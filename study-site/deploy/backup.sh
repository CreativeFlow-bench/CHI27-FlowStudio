#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATABASE="$ROOT/data/study.sqlite3"
BACKUP_DIR="$ROOT/backups"

[[ -f "$DATABASE" ]] || exit 0
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
sqlite3 "$DATABASE" ".timeout 10000" ".backup '$BACKUP_DIR/study-$STAMP.sqlite3'"
gzip "$BACKUP_DIR/study-$STAMP.sqlite3"
find "$BACKUP_DIR" -type f -name 'study-*.sqlite3.gz' -mtime +14 -delete
