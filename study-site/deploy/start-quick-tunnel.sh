#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLOUDFLARED="${CLOUDFLARED_BIN:-$HOME/bin/cloudflared}"
PID_FILE="$ROOT/run/cloudflared.pid"
LOG_FILE="$ROOT/logs/cloudflared.log"

mkdir -p "$ROOT/run" "$ROOT/logs"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  exit 0
fi

: > "$LOG_FILE"
nohup "$CLOUDFLARED" tunnel --no-autoupdate --url http://127.0.0.1:${PORT:-5190} >> "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"

for _ in {1..30}; do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" | head -1 || true)"
  if [[ -n "$URL" ]]; then
    printf '%s\n' "$URL" > "$ROOT/run/public-url.txt"
    printf '%s\n' "$URL"
    exit 0
  fi
  sleep 1
done

echo "Cloudflare Quick Tunnel did not produce a URL" >&2
exit 1
