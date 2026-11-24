#!/bin/sh
set -eu
umask 077
if [ -e .env ]; then
    printf '%s\n' '.env already exists.'
    exit 0
fi
(
    set -C
    printf 'POSTGRES_PASSWORD=%s\nFACTORYIQ_OPERATOR_TOKEN=%s\nFACTORYIQ_DEMO_READS=true\nFACTORYIQ_READ_ONLY=false\n' \
        "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" > .env
)
printf '%s\n' 'Created .env with unique local credentials.'
