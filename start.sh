#!/bin/sh
# Railway injects PORT. Local Docker / Compose may set APP_PORT.
# Never hardcode 43147 here — Generate Service Domain must match this listen port.
set -e
PORT="${PORT:-${APP_PORT:-8080}}"
echo "kintrafic-live: uvicorn 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --proxy-headers --forwarded-allow-ips='*'
