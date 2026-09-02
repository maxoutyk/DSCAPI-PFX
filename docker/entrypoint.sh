#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Ensuring cache table exists..."
python manage.py createcachetable

echo "Collecting static files..."
python manage.py collectstatic --noinput

if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  echo "Ensuring Django admin user exists..."
  python manage.py bootstrap_admin
fi

echo "Starting Gunicorn..."
# Access logs to stdout → Azure Log Analytics (ContainerAppConsoleLogs).
# x-forwarded-for = real client IP behind ACA ingress; %(D)s = request time (µs).
exec gunicorn DSCApi.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile - \
  --access-logformat '%({x-forwarded-for}i)s %(h)s %(t)s "%(r)s" %(s)s %(b)s "%(a)s" %(D)s'
