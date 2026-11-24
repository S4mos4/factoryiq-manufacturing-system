#!/bin/sh
set -eu
umask 077
check_secret() {
    case "$1" in ''|*[!a-f0-9]*) echo 'MQTT secrets must be random lowercase hexadecimal values.' >&2; exit 1;; esac
    [ "${#1}" -ge 32 ] || { echo 'MQTT secrets must have at least 32 hex characters.' >&2; exit 1; }
}
check_secret "${FACTORYIQ_MQTT_BRIDGE_PASSWORD:?Set FACTORYIQ_MQTT_BRIDGE_PASSWORD}"
check_secret "${FACTORYIQ_MQTT_DEVICE_SECRET:?Set FACTORYIQ_MQTT_DEVICE_SECRET}"
broker_dir="$(mktemp -d)"
printf 'bridge:%s\n' "$FACTORYIQ_MQTT_BRIDGE_PASSWORD" > "$broker_dir/passwords"
for device in sim-conveyor sim-sorter sim-robot sim-hydraulic sim-line sim-motor; do
    digest="$(printf '%s:%s' "$FACTORYIQ_MQTT_DEVICE_SECRET" "$device" | sha256sum)"
    printf '%s:%s\n' "$device" "${digest%% *}" >> "$broker_dir/passwords"
done
if [ -n "${FACTORYIQ_ESP32_PASSWORD:-}" ]; then
    check_secret "$FACTORYIQ_ESP32_PASSWORD"
    esp32_id="${FACTORYIQ_ESP32_DEVICE_ID:-esp32-prototype}"
    printf '%s\n' "$esp32_id" | grep -Eq '^esp32-[a-z0-9][a-z0-9-]{0,32}$' ||
        { echo 'Invalid ESP32 device identifier.' >&2; exit 1; }
    printf '%s:%s\n' "$esp32_id" "$FACTORYIQ_ESP32_PASSWORD" >> "$broker_dir/passwords"
fi
mosquitto_passwd -U "$broker_dir/passwords"
cat > "$broker_dir/acl" <<'ACL'
user bridge
topic read factoryiq/device/+/telemetry
topic read factoryiq/device/+/heartbeat
pattern write factoryiq/device/%u/telemetry
pattern write factoryiq/device/%u/heartbeat
ACL
cat > "$broker_dir/mosquitto.conf" <<CONFIG
allow_anonymous false
password_file $broker_dir/passwords
acl_file $broker_dir/acl
listener ${FACTORYIQ_MQTT_PORT:-1883} ${FACTORYIQ_MQTT_BIND:-0.0.0.0}
max_packet_size 8192
max_queued_messages 256
persistent_client_expiration 1d
log_type error
log_type warning
CONFIG
if [ "${FACTORYIQ_MQTT_LAN_TLS:-false}" = true ]; then
    cat >> "$broker_dir/mosquitto.conf" <<CONFIG
listener 8883
certfile /run/factoryiq-tls/server.crt
keyfile /run/factoryiq-tls/server.key
tls_version tlsv1.2
CONFIG
fi
if [ "$(id -u)" -eq 0 ]; then
    chown -R mosquitto:mosquitto "$broker_dir"
fi
exec mosquitto -c "$broker_dir/mosquitto.conf"
