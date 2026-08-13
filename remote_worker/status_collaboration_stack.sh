#!/usr/bin/env bash
set -euo pipefail

API_KEY_FILE="${CF_API_KEY_FILE:-/root/.creativeflow_api_v1.key}"
key=""
if [[ -s "$API_KEY_FILE" ]]; then
  key="$(cat "$API_KEY_FILE")"
fi

probe() {
  local label="$1"
  local url="$2"
  shift 2
  local status
  status="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 20 "$@" "$url" || true)"
  printf '%-24s %s\n' "$label" "$status"
}

probe "CreativeFlow API" "http://127.0.0.1:18080/api/v1/variations/capabilities" \
  -H "X-CreativeFlow-Key: $key"
probe "Qwen-Image" "http://127.0.0.1:18082/health"
probe "Qwen2.5-VL" "http://127.0.0.1:18084/health"
probe "Wikidata via proxy" \
  "https://www.wikidata.org/w/api.php?action=wbsearchentities&search=lantern&language=en&format=json&limit=1" \
  --proxy "http://127.0.0.1:33210"
probe "Getty AAT" "https://vocab.getty.edu/aat/300037680.json"

nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
