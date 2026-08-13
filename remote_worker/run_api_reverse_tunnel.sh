#!/usr/bin/env bash
set -euo pipefail

: "${CF_GATEWAY_HOST:=93.127.141.73}"
: "${CF_GATEWAY_SSH_PORT:=10053}"
: "${CF_GATEWAY_USER:=administrator}"
: "${CF_GATEWAY_KEY:=/root/.ssh/creativeflow_proxy_ed25519}"
: "${CF_GATEWAY_API_PORT:=18080}"
: "${CF_LOCAL_API_PORT:=18080}"
: "${CF_LOCAL_HTTP_PROXY_PORT:=33210}"
: "${CF_GATEWAY_HTTP_PROXY_PORT:=3128}"
: "${CF_LOCAL_SOCKS_PROXY_PORT:=33211}"

while true; do
  ssh \
    -N \
    -T \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=accept-new \
    -i "$CF_GATEWAY_KEY" \
    -p "$CF_GATEWAY_SSH_PORT" \
    -L "127.0.0.1:${CF_LOCAL_HTTP_PROXY_PORT}:127.0.0.1:${CF_GATEWAY_HTTP_PROXY_PORT}" \
    -D "127.0.0.1:${CF_LOCAL_SOCKS_PROXY_PORT}" \
    -R "127.0.0.1:${CF_GATEWAY_API_PORT}:127.0.0.1:${CF_LOCAL_API_PORT}" \
    "${CF_GATEWAY_USER}@${CF_GATEWAY_HOST}" || true
  sleep 5
done
