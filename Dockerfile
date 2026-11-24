FROM node:24-bookworm-slim@sha256:873f586f3794f52281bd039bf02c048a0be08fde619338f9941bad1eb6b34530 AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.15-slim-bookworm@sha256:498829c717b1e59fc42f0e7865eafe4e04ca0f70a3769d4ae70ba218df54507c
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FACTORYIQ_STATIC_DIR=/app/web
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system factoryiq \
    && useradd --system --gid factoryiq factoryiq
COPY backend/ ./
COPY --from=frontend /build/dist /app/web
COPY scripts/start-container.sh /usr/local/bin/start-factoryiq
USER factoryiq
EXPOSE 8000
ENTRYPOINT ["sh", "/usr/local/bin/start-factoryiq"]
