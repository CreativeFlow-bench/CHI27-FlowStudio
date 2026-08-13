#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! curl --fail --silent --max-time 5 http://127.0.0.1:${PORT:-5190}/api/health >/dev/null; then
  "$ROOT/deploy/stop.sh" || true
  "$ROOT/deploy/start.sh"
fi
