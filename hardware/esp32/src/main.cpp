#include <Arduino.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <esp_system.h>
#include <math.h>
#include <time.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace {
constexpr int sdaPin = 21;
constexpr int sclPin = 22;
constexpr int proximityPin = 27;
constexpr uint8_t temperatureAddress = 0x48;
constexpr uint8_t accelerometerAddress = 0x53;
constexpr uint8_t energyAddress = 0x40;
constexpr unsigned long publishMs = 3000;
constexpr unsigned long reconnectMs = 5000;
constexpr float gravityScale = 0.0039f;
constexpr float shuntOhms = 0.1f;  // Adafruit INA219 breakout with an R100 shunt
constexpr time_t earliestClock = 1767225600;  // Reject the uninitialised Unix clock.

WiFiClientSecure transport;
MQTTClient mqtt(768);
String heartbeatTopic, telemetryTopic;
unsigned long lastWifiRetry = 0, lastBrokerRetry = 0, lastRead = 0, lastAccel = 0;
unsigned long lastEdge = 0;
bool stableReed = HIGH, rawReed = HIGH;
uint32_t count = 0;
time_t previousTimestamp = 0;
bool accelerometerConfigured = false;
bool haveCompleteWindow = false;
bool configured = false;

struct Acceleration {
    float sum[3]{};
    float squares[3]{};
    unsigned samples = 0;

    void add(const uint8_t *bytes) {
        for (unsigned axis = 0; axis < 3; ++axis) {
            auto encoded = uint16_t(bytes[2 * axis]) | (uint16_t(bytes[2 * axis + 1]) << 8);
            float g = int16_t(encoded) * gravityScale;
            sum[axis] += g;
            squares[axis] += g * g;
        }
        ++samples;
    }

    float rms() const {
        if (samples < 8) return NAN;
        float variance = 0;
        for (unsigned axis = 0; axis < 3; ++axis) {
            float mean = sum[axis] / samples;
            variance += fmaxf(0, squares[axis] / samples - mean * mean);
        }
        return sqrtf(variance);
    }
} acceleration;

bool fetch(uint8_t address, uint8_t reg, uint8_t *out, uint8_t size) {
    Wire.beginTransmission(address);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0 || Wire.requestFrom(address, size) != size) return false;
    for (uint8_t i = 0; i < size; ++i) out[i] = Wire.read();
    return true;
}

bool writeRegister(uint8_t address, uint8_t reg, uint8_t value) {
    Wire.beginTransmission(address);
    Wire.write(reg);
    Wire.write(value);
    return Wire.endTransmission() == 0;
}

uint16_t bigEndian(const uint8_t *data) {
    return (uint16_t(data[0]) << 8) | data[1];
}

float temperature() {
    uint8_t bytes[2];
    if (!fetch(temperatureAddress, 0x00, bytes, sizeof(bytes))) return NAN;
    return int16_t(bigEndian(bytes)) * 0.0078125f + temperatureOffsetC;
}

void updateAcceleration() {
    uint8_t bytes[6];
    if (!accelerometerConfigured) {
        uint8_t identity;
        accelerometerConfigured = fetch(accelerometerAddress, 0x00, &identity, 1) &&
            identity == 0xe5 && writeRegister(accelerometerAddress, 0x31, 0x08) &&
            writeRegister(accelerometerAddress, 0x2c, 0x0a) &&
            writeRegister(accelerometerAddress, 0x2d, 0x08);
    }
    if (accelerometerConfigured && fetch(accelerometerAddress, 0x32, bytes, sizeof(bytes))) {
        acceleration.add(bytes);
    } else {
        accelerometerConfigured = false;
    }
}

void updateProximity(unsigned long now) {
    bool level = digitalRead(proximityPin);
    if (level != rawReed) {
        rawReed = level;
        lastEdge = now;
    }
    if (level != stableReed && now - lastEdge >= 30) {
        stableReed = level;
        if (level == LOW) ++count;
    }
}

void readPower(JsonDocument &reading) {
    uint8_t bus[2], shunt[2];
    if (!enableIna219 || !fetch(energyAddress, 0x02, bus, 2) ||
        !fetch(energyAddress, 0x01, shunt, 2)) return;
    const uint16_t busRaw = bigEndian(bus);
    if ((busRaw & 1) || !(busRaw & 2)) return;  // overflow or conversion not ready
    float volts = (busRaw >> 3) * 0.004f;
    float amps = int16_t(bigEndian(shunt)) * 0.00001f / shuntOhms;
    if (amps < 0) return;  // Forward-only electrical model
    reading["voltage_v"] = volts;
    reading["current_a"] = amps;
    reading["power_w"] = volts * amps;
}

void publish(time_t observed) {
    struct tm utc;
    gmtime_r(&observed, &utc);
    char stamp[25];
    strftime(stamp, sizeof(stamp), "%Y-%m-%dT%H:%M:%SZ", &utc);
    JsonDocument message;
    message["schema_version"] = 1;
    message["device_id"] = deviceId;
    message["observed_at"] = stamp;
    String payload;
    serializeJson(message, payload);
    mqtt.publish(heartbeatTopic, payload, false, 1);

    if (previousTimestamp && observed - previousTimestamp < 3) return;
    char id[37];
    snprintf(id, sizeof(id), "%08lx-%04lx-4%03lx-8%03lx-%08lx%04lx",
             (unsigned long)esp_random(), (unsigned long)(esp_random() & 0xffff),
             (unsigned long)(esp_random() & 0xfff), (unsigned long)(esp_random() & 0xfff),
             (unsigned long)esp_random(), (unsigned long)(esp_random() & 0xffff));
    message["message_id"] = id;
    message["interval_seconds"] = 3;
    message["status"] = "unknown";
    float temp = temperature();
    float vibration = acceleration.rms();
    if (isfinite(temp)) message["temperature_c"] = temp;
    if (isfinite(vibration)) message["vibration_g"] = vibration;
    if (!isfinite(temp) || !isfinite(vibration)) message["fault"] = "sensor_disconnected";
    if (enableProximity && haveCompleteWindow && observed - previousTimestamp == 3)
        message["produced"] = count;
    readPower(message);
    payload = "";
    serializeJson(message, payload);
    haveCompleteWindow = mqtt.publish(telemetryTopic, payload, false, 1);
    previousTimestamp = observed;
    count = 0;
    acceleration = Acceleration{};
}
}  // namespace

void setup() {
    Serial.begin(115200);
    Wire.begin(sdaPin, sclPin, 100000);
    if (enableProximity) pinMode(proximityPin, INPUT_PULLUP);
    if (!wifiSsid[0] || !mqttHost[0] || !mqttPassword[0] || !brokerCa[0]) {
        Serial.println("Configure include/secrets.h before connecting.");
        return;
    }
    configured = true;
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(wifiSsid, wifiPassword);
    configTime(0, 0, ntpHost);
    transport.setCACert(brokerCa);
    transport.setHandshakeTimeout(4);
    mqtt.begin(mqttHost, 8883, transport);
    mqtt.setOptions(15, true, 1200);
    const String base = String("factoryiq/device/") + deviceId;
    heartbeatTopic = base + "/heartbeat";
    telemetryTopic = base + "/telemetry";
}

void loop() {
    if (!configured) {
        delay(500);
        return;
    }
    unsigned long now = millis();
    time_t observed = time(nullptr);
    if (enableProximity) updateProximity(now);
    if (now - lastAccel >= 10) {
        lastAccel = now;
        updateAcceleration();
    }
    if (WiFi.status() != WL_CONNECTED) {
        haveCompleteWindow = false;
        if (now - lastWifiRetry >= reconnectMs) {
            lastWifiRetry = now;
            WiFi.reconnect();
        }
    } else if (observed >= earliestClock) {
        if (!mqtt.connected()) {
            haveCompleteWindow = false;
            if (now - lastBrokerRetry >= reconnectMs) {
                lastBrokerRetry = now;
                mqtt.connect(deviceId, deviceId, mqttPassword);
            }
        } else {
            mqtt.loop();
            if (now - lastRead >= publishMs) {
                lastRead = now;
                publish(observed);
            }
        }
    }
    delay(2);
}
