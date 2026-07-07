# ───────── LBAMonitor Backend Dockerfile v4.3 ─────────
# Multi-stage build para minimizar tamaño de imagen final

FROM python:3.12-slim-bookworm AS builder

# Instalar dependencias del sistema necesarias para compilar wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar solo pyproject.toml para cachear dependencias
COPY backend/pyproject.toml ./
COPY backend/lbamonitor ./lbamonitor
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY backend/plugins ./plugins

# Instalar dependencias
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# ───────── Final stage ─────────
FROM python:3.12-slim-bookworm AS runtime

# Instalar runtime mínimo
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 lbamonitor

WORKDIR /app

# Copiar paquetes instalados del builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Directorios de datos
RUN mkdir -p /data /logs /backups && chown -R lbamonitor:lbamonitor /data /logs /backups /app

USER lbamonitor

ENV LBAMONITOR_ENV=production \
    LBAMONITOR_DATABASE__ENGINE=postgresql \
    LBAMONITOR_DATABASE__PATH=lbamonitor \
    LBAMONITOR_DATABASE__HOST=db \
    LBAMONITOR_DATABASE__PORT=5432 \
    PYTHONUNBUFFERED=1

EXPOSE 8123

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8123/health', timeout=3)" || exit 1

CMD ["uvicorn", "lbamonitor.api.main:app", "--host", "0.0.0.0", "--port", "8123", "--workers", "1"]
