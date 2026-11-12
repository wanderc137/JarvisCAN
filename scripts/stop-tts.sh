#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
PID_FILE="$ROOT/data/tts-server.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$PID" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null || true
    fi
    echo "Servidor de voz detenido (PID $PID)."
  else
    echo "El PID del servidor de voz ya no estaba activo."
  fi
  rm -f "$PID_FILE"
else
  if pkill -f "$ROOT/scripts/tts-server.py" 2>/dev/null; then
    echo "Servidor de voz detenido."
  else
    echo "El servidor de voz no estaba corriendo."
  fi
fi
