#!/usr/bin/env bash
set -e

# Go to this script's directory (repo root)
cd "$(dirname "$0")"

# Activate venv
source .venv/bin/activate

# Start Flask in the background
python webapp/app.py &
SERVER_PID=$!

# Give Flask a moment to start
sleep 1

# Open Chrome to the site (fallback: default browser)
open -a "Google Chrome" "http://127.0.0.1:5050" || open "http://127.0.0.1:5050"

echo "ThreadTally running (PID=$SERVER_PID). Press Ctrl+C here to stop."
wait $SERVER_PID
