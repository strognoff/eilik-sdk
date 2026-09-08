#!/usr/bin/env bash
# ensure_eilik_service.sh — idempotently start (or restart) the Eilik
# FastAPI HTTP service in the background. The service itself uses on-demand
# serial sessions, so keeping this API process alive does not keep Eilik's USB
# control session or keepalive loop open.
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
STATE_FILE="${STATE_FILE:-/home/cechinel/.openclaw/workspace/state/eilik_watchdog.json}"

mkdir -p "$(dirname "$LOG")"
mkdir -p "$(dirname "$STATE_FILE")"
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

# Update state file in place. Args: action, port (may be empty).
write_state() {
  local action="$1"
  local port="$2"
  "$VENV_PY" - "$STATE_FILE" "$action" "$port" <<'PY' 2>/dev/null || true
import json, os, sys
from datetime import datetime, timezone

path, action, port = sys.argv[1], sys.argv[2], sys.argv[3]
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
d = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        d = {}
prev_skips = int(d.get("consecutive_skips", 0) or 0)
if action in ("healthy_fastpath", "restarted"):
    new_skips = 0
elif action == "skipped_no_usb":
    new_skips = prev_skips + 1
else:
    new_skips = prev_skips
d.update({
    "last_action": action,
    "consecutive_skips": new_skips,
    "last_action_at": now,
    "port": port or d.get("port"),
})
with open(path, "w") as f:
    json.dump(d, f, indent=2)
PY
}

# 1. Health check first — fast path
if curl -sS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
  write_state "healthy_fastpath" ""
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
    write_state "skipped_no_usb" ""
    exit 0
  fi
fi

# 4. Start fresh. Use setsid so the agent shell exiting does not take uvicorn
# down with it; the HTTP API itself uses on-demand serial sessions.
cd "$SDK_DIR"
setsid -f "$VENV_PY" -u -m eilik serve --port "$PORT" --port-http "$HTTP_PORT" \
  > /tmp/eilik-service.log 2>&1 < /dev/null
sleep 1
new_pid="$(ss -tlnp 2>/dev/null | grep ":${HTTP_PORT}" | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true)"
log "[ensure_eilik_service] started pid=${new_pid:-unknown} port=$PORT http=$HTTP_PORT"

# 5. Give it a moment, verify
sleep 5
if curl -sS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
  log "[ensure_eilik_service] healthy after restart"
else
  log "[ensure_eilik_service] STILL UNHEALTHY after restart — manual intervention required"
fi
write_state "restarted" "$PORT"
exit 0
