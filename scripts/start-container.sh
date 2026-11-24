#!/bin/sh
set -eu

if [ "${FACTORYIQ_BOOTSTRAP:-false}" = true ]; then
    alembic upgrade head
fi
if [ "${FACTORYIQ_SEED:-false}" = true ]; then
    python -m factoryiq.seed
fi
exec uvicorn factoryiq.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-proxy-headers
