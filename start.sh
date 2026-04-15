#!/usr/bin/env bash
# Railway / Railpack: run from repo root (same directory as this script).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}/forma_project"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-forma_project.settings}"
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn forma_project.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}"
