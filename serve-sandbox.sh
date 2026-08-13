#!/bin/bash
# Start a static HTTP server for the FlowStudio sandbox files.
# Usage: ./serve-sandbox.sh [PORT]

PORT=${1:-8765}
DIR="$(cd "$(dirname "$0")" && pwd)"

# Check if something is already on the port
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "Port $PORT already in use - checking our server"
  curl -s -o /dev/null -w "Status: %{http_code}\n" http://127.0.0.1:$PORT/intent-ir-sandbox.html
  exit 0
fi

# Start server in background
cd "$DIR" && python3 -m http.server $PORT --bind 127.0.0.1 > /tmp/sandbox-server.log 2>&1 &
SERVER_PID=$!
echo "Sandbox server started: PID=$SERVER_PID on port $PORT"
echo "$SERVER_PID" > /tmp/sandbox-server.pid

sleep 1
echo "Test: http://127.0.0.1:$PORT/intent-ir-sandbox.html"
curl -s -o /dev/null -w "Status: %{http_code}\n" http://127.0.0.1:$PORT/intent-ir-sandbox.html
