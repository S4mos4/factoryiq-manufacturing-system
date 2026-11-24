#!/bin/sh
set -eu
umask 077
if [ -e .env ]; then
    for setting in FACTORYIQ_MQTT_BRIDGE_PASSWORD FACTORYIQ_MQTT_DEVICE_SECRET; do
        if ! grep -q "^$setting=" .env; then
            printf '%s=%s\n' "$setting" "$(openssl rand -hex 24)" >> .env
        fi
    done
    printf '%s\n' '.env is ready.'
    exit 0
fi
(
    set -C
    printf 'POSTGRES_PASSWORD=%s\nFACTORYIQ_OPERATOR_TOKEN=%s\nFACTORYIQ_DEMO_READS=true\nFACTORYIQ_READ_ONLY=false\nFACTORYIQ_MQTT_BRIDGE_PASSWORD=%s\nFACTORYIQ_MQTT_DEVICE_SECRET=%s\n' \
        "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" \
        "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" > .env
)
printf '%s\n' 'Created .env with unique local credentials.'
