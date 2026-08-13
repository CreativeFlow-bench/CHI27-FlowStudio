#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE="${NODE_BIN:-$ROOT/runtime/node/bin/node}"
PID_FILE="$ROOT/run/app.pid"

mkdir -p "$ROOT/run" "$ROOT/logs" "$ROOT/data" "$ROOT/backups"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  exit 0
fi

cd "$ROOT"
nohup env PORT="${PORT:-5190}" "$NODE" src/server.js >> "$ROOT/logs/app.log" 2>&1 < /dev/null &
echo $! > "$PID_FILE"
