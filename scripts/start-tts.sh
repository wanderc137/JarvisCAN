#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
PORT="${TTS_PORT:-8090}"
PID_FILE="$ROOT/data/tts-server.pid"
LOG="$ROOT/data/tts-server.log"
mkdir -p "$ROOT/data"

if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
  echo "Panel de alertas ya activo en el puerto $PORT."
else
  nohup python3 "$ROOT/scripts/tts-server.py" --port "$PORT" >"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
  ok=0
  for _ in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 0.25
  done
  if [ "$ok" -ne 1 ]; then
    echo "No se pudo iniciar el panel de alertas. Revisá $LOG" >&2
    exit 1
  fi
  echo "Panel de alertas iniciado en el puerto $PORT."
fi

IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
[ -n "$IP" ] || IP="$(hostname -I | awk '{print $1}')"
echo "Abrí el panel de alertas en el navegador: http://$IP:$PORT/"
echo "Tocá 'Activar sonido' y dejá la página abierta."
