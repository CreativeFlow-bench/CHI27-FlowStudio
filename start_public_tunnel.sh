#!/usr/bin/env bash
# FlowStudio public experiment tunnel: nginx (8080) + cloudflared quick tunnel
set -euo pipefail
cd /root/flowstudio_app
if ! pgrep -x nginx >/dev/null; then nginx; fi
cd /root/flowstudio_app/cloudflare
if ! pgrep -f "cloudflared tunnel" >/dev/null; then
  nohup ./cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080 > /root/flowstudio_app/logs/cloudflared.log 2>&1 &
fi
for i in $(seq 1 30); do
  url=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /root/flowstudio_app/logs/cloudflared.log | head -1 || true)
  if [ -n "$url" ]; then echo "PUBLIC_URL=$url"; break; fi
  sleep 2
done
