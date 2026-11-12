#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
URL="${JARVIS_CAM_AUDIO_URL:-http://192.168.1.198:8080/audio.wav}"

"$ROOT/scripts/start-tts.sh" || echo "Aviso: no se pudo iniciar el servidor de voz." >&2
exec "$ROOT/scripts/voice-can.sh" --url "$URL" "$@"
