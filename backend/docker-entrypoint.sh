#!/bin/sh
# Wait for MySQL to be ready, run migrations, then exec the CMD.
set -e

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"

echo "[entrypoint] Waiting for MySQL at ${DB_HOST}:${DB_PORT} ..."
until nc -z "${DB_HOST}" "${DB_PORT}"; do
  sleep 2
done
echo "[entrypoint] MySQL is ready."

echo "[entrypoint] Applying migrations ..."
python manage.py migrate --noinput

echo "[entrypoint] Starting application: $*"
exec "$@"
