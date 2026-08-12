#!/usr/bin/env bash
# ensure_eilik_service.sh — idempotently start (or restart) the Eilik
# FastAPI service in the background. Designed to be called from a cron
# every few minutes to keep the service alive through USB unplug/replug,
# stale port, or other transient failures.
#
# Usage:
#   ensure_eilik_service.sh
#
# Behavior:
#   - If /health returns 200 OK on $HEALTH_URL, exit 0 silently.
#   - Otherwise kill any leftover uvicorn eilik process, restart fresh,
#     and log to $LOG.

set -u

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8765/health}"
PORT="${PORT:-/dev/ttyACM1}"
HTTP_PORT="${HTTP_PORT:-8765}"
LOG="${LOG:-/tmp/eilik-service.watchdog.log}"
SDK_DIR="${SDK_DIR:-/home/cechinel/.openclaw/workspace/eilik-sdk}"
VENV_PY="${SDK_DIR}/.venv/bin/python"

mkdir -p "$(dirname "$LOG")"
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

# 1. Health check first — fast path
if curl -sS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
  exit 0
fi

log "[ensure_eilik_service] unhealthy, restarting"

# 2. Kill any leftover eilik uvicorn process (by port, not pkill)
for pid in $(ss -tlnp 2>/dev/null | grep ":${HTTP_PORT}" | grep -oE 'pid=[0-9]+' | head -3 | cut -d= -f2); do
  kill "$pid" 2>/dev/null && log "[ensure_eilik_service] killed pid=$pid"
done
sleep 2

# 3. Auto-detect port if ACM1 missing
if [ ! -e "$PORT" ]; then
  DETECTED=$("$VENV_PY" -c "from eilik.controller import EilikController; print(EilikController.detect_port())" 2>/dev/null || echo "")
  if [ -n "$DETECTED" ] && [ -e "$DETECTED" ]; then
    PORT="$DETECTED"
    log "[ensure_eilik_service] auto-detected port=$PORT"
  else
    log "[ensure_eilik_service] no Eilik USB device present, skipping restart"
    exit 0
  fi
fi

# 4. Start fresh
cd "$SDK_DIR"
nohup "$VENV_PY" -u -m eilik serve --port "$PORT" --port-http "$HTTP_PORT" \
  > /tmp/eilik-service.log 2>&1 &
disown
log "[ensure_eilik_service] started pid=$! port=$PORT http=$HTTP_PORT"

# 5. Give it a moment, verify
sleep 5
if curl -sS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
  log "[ensure_eilik_service] healthy after restart"
else
  log "[ensure_eilik_service] STILL UNHEALTHY after restart — manual intervention required"
fi
exit 0
