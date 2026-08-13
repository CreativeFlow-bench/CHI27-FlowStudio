#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER="# chi27-flowstudio-study"
CURRENT="$(crontab -l 2>/dev/null | grep -vF "$MARKER" || true)"
{
  printf '%s\n' "$CURRENT"
  printf '@reboot %q/deploy/start.sh >> %q/logs/boot.log 2>&1 %s\n' "$ROOT" "$ROOT" "$MARKER"
  printf '@reboot %q/deploy/start-quick-tunnel.sh >> %q/logs/boot.log 2>&1 %s\n' "$ROOT" "$ROOT" "$MARKER"
  printf '* * * * * %q/deploy/watchdog.sh >> %q/logs/watchdog.log 2>&1 %s\n' "$ROOT" "$ROOT" "$MARKER"
  printf '* * * * * %q/deploy/watchdog-tunnel.sh >> %q/logs/watchdog.log 2>&1 %s\n' "$ROOT" "$ROOT" "$MARKER"
  printf '*/10 * * * * %q/deploy/backup.sh >> %q/logs/backup.log 2>&1 %s\n' "$ROOT" "$ROOT" "$MARKER"
} | sed '/^[[:space:]]*$/d' | crontab -
