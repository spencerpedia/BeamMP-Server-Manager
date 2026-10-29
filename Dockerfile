# ---- frontend build ----
# Built on the native platform: the output is plain static files, so no emulation is needed.
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
# Debian 12 base matches the BeamMP-Server.debian.12 release binaries.
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/spencerpedia/BeamMP-Server-Manager" \
      org.opencontainers.image.description="Crafty-style web panel for running multiple BeamMP servers" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    BACKUP_DIR=/backups \
    IMPORT_DIR=/import \
    STATIC_DIR=/app/static \
    GAME_PORT_RANGE=30814-30823 \
    PUID=99 \
    PGID=100 \
    TZ=UTC

RUN apt-get update \
 && apt-get install -y --no-install-recommends tini ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=ui /ui/dist ./static
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/data", "/backups"]
EXPOSE 8000/tcp 30814-30823/tcp 30814-30823/udp

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
