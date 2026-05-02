#!/usr/bin/env bash
# Railway / Railpack: run from repo root (same directory as this script).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}/forma_project"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-forma_project.settings}"

# Ensure testimonial .mov transcoding can find ffmpeg in Railway.
if [ -z "${IMAGEIO_FFMPEG_EXE:-}" ]; then
  if command -v ffmpeg >/dev/null 2>&1; then
    export IMAGEIO_FFMPEG_EXE="$(command -v ffmpeg)"
  else
    _IMAGEIO_FFMPEG_EXE="$(python - <<'PY'
try:
    import imageio_ffmpeg
    path = imageio_ffmpeg.get_ffmpeg_exe()
    print(path if path else "")
except Exception:
    print("")
PY
)"
    if [ -n "${_IMAGEIO_FFMPEG_EXE}" ] && [ -x "${_IMAGEIO_FFMPEG_EXE}" ]; then
      export IMAGEIO_FFMPEG_EXE="${_IMAGEIO_FFMPEG_EXE}"
    fi
  fi
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput
# Recycle workers after a bounded number of requests to limit unbounded memory growth
# in long-running processes (GUNICORN_MAX_REQUESTS=0 disables). Jitter spreads restarts.
: "${GUNICORN_MAX_REQUESTS:=2000}"
: "${GUNICORN_MAX_REQUESTS_JITTER:=200}"
_MAX_REQ_ARGS=()
if [ "${GUNICORN_MAX_REQUESTS}" -gt 0 ] 2>/dev/null; then
  _MAX_REQ_ARGS=(--max-requests "${GUNICORN_MAX_REQUESTS}" --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-0}")
fi
exec gunicorn forma_project.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  "${_MAX_REQ_ARGS[@]}"
