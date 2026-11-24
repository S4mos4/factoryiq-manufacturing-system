import hashlib
import logging
import os
from threading import Event

from paho.mqtt import client as mqtt
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from .protocol import MAX_PAYLOAD, TOPIC_PREFIX, Heartbeat, Reading
from .store import save_heartbeat, save_reading

log = logging.getLogger(__name__)


def derived_password(device, secret=None):
    secret = secret if secret is not None else os.environ["FACTORYIQ_MQTT_DEVICE_SECRET"]
    if len(secret) < 32:
        raise ValueError("MQTT device secret must contain at least 32 characters.")
    return hashlib.sha256(f"{secret}:{device}".encode()).hexdigest()


def mqtt_client(username, password, *, subscriber=False, host=None, port=None):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=("factoryiq-"+username),
                         clean_session=not subscriber,manual_ack=subscriber)
    client.username_pw_set(username,password)
    client.reconnect_delay_set(min_delay=1,max_delay=20)
    client.max_queued_messages_set(32)
    ca = os.getenv("FACTORYIQ_MQTT_CA")
    if ca:
        client.tls_set(ca_certs=ca)
    client.connect_async(host or os.getenv("FACTORYIQ_MQTT_HOST","127.0.0.1"),
                         port or int(os.getenv("FACTORYIQ_MQTT_PORT","1883")),keepalive=15)
    return client


def ingest(topic, payload, *, retained=False):
    head, separator, kind = topic.rpartition("/")
    if not separator or retained or len(payload)>MAX_PAYLOAD:
        return "invalid"
    prefix, _, username = head.rpartition("/")
    if prefix != TOPIC_PREFIX or kind not in {"telemetry","heartbeat"}:
        return "invalid"
    try:
        message = (Reading if kind=="telemetry" else Heartbeat).model_validate_json(payload)
    except ValidationError:
        return "invalid"
    if username != message.device_id:
        return "identity_mismatch"
    return save_reading(message) if kind=="telemetry" else save_heartbeat(message)


def subscriber(password, retry: Event, host=None, port=None):
    client = mqtt_client("bridge",password,subscriber=True,host=host,port=port)

    def connected(client, _userdata, _flags, reason, _properties):
        if reason.is_failure:
            log.warning("MQTT subscriber connection rejected: %s",reason)
            return
        client.subscribe([(f"{TOPIC_PREFIX}/+/telemetry",1),(f"{TOPIC_PREFIX}/+/heartbeat",1)])

    def received(client, _userdata, message):
        try:
            outcome = ingest(message.topic,message.payload,retained=message.retain)
        except OperationalError:
            # No ACK on transient storage errors. Rejoin the persistent session to receive the message again.
            retry.set()
            log.warning("MQTT ingestion unavailable; reconnecting the subscriber.")
            return
        if outcome in {"invalid","identity_mismatch","unknown_device","overlap"}:
            log.debug("Discarded MQTT message: %s",outcome)
        if message.qos:
            client.ack(message.mid,message.qos)

    client.on_connect = connected
    client.on_message = received
    return client
