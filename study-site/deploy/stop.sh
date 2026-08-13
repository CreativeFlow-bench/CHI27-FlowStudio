#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/run/app.pid"

mkdir -p "$ROOT/run"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  kill "$(cat "$PID_FILE")"
  for _ in {1..20}; do
    kill -0 "$(cat "$PID_FILE")" 2>/dev/null || break
    sleep 0.25
  done
fi
: > "$PID_FILE"
