# ============================================================
# Stage 1 — build dependencies
# ============================================================
FROM python:3.11-slim AS builder

# System packages needed to compile mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        pkg-config \
        default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ============================================================
# Stage 2 — lean runtime image
# ============================================================
FROM python:3.11-slim AS runtime

# Runtime MySQL client library only (no compiler needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — OpenShift by default runs containers as arbitrary UID,
# but we still define a named user for local/plain-Docker runs.
RUN useradd -m -u 1001 appuser

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Pre-collect static files so WhiteNoise can serve them
# DB_NAME is set to 'dummy' only for collectstatic (no DB access needed)
RUN DB_NAME=dummy DB_USER=dummy DB_PASSWORD=dummy DB_HOST=localhost \
    python manage.py collectstatic --noinput

# OpenShift grants arbitrary UIDs write access to the working directory;
# ensure the group (root, gid=0) can write logs/tmp inside /app.
RUN chown -R 1001:0 /app && chmod -R g=u /app

USER 1001

EXPOSE 8000

# Entrypoint: wait for MySQL, run migrations, then start gunicorn
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn", "backend.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
