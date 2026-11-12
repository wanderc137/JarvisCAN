#!/usr/bin/env bash
# run-service-tts.sh — panel web de alertas bajo systemd.
# Escribe el PID file que usan stop-tts.sh y status-tts.sh.
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
mkdir -p data
echo $$ > "$ROOT/data/tts-server.pid"
exec /usr/bin/python3 "$ROOT/scripts/tts-server.py" --port "${TTS_PORT:-8090}"
