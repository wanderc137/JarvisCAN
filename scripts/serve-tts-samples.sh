#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
PORT="${TTS_SAMPLES_PORT:-8092}"
DIR="$ROOT/data/tts-samples"
PID_FILE="$ROOT/data/tts-samples.pid"
LOG="$ROOT/data/tts-samples.log"
mkdir -p "$DIR"

ip_address() {
  local ip
  ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
  [ -n "$ip" ] || ip="$(hostname -I | awk '{print $1}')"
  printf '%s' "$ip"
}

stop_server() {
  if [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.3
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
  pkill -f "http.server $PORT" 2>/dev/null || true
}

if [ "${1:-}" = "--stop" ]; then
  stop_server
  echo "Servidor de muestras detenido (puerto $PORT)."
  exit 0
fi

python3 - "$DIR" <<'PY'
import html
import sys
from pathlib import Path

out = Path(sys.argv[1])
wavs = sorted(p.name for p in out.glob("*.wav"))
rows = []
for name in wavs:
    label = name[:-4].replace("_", " ")
    rows.append(
        f'<li><strong>{html.escape(label)}</strong><br>'
        f'<audio controls preload="none" src="{html.escape(name)}"></audio></li>'
    )
page = f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Muestras TTS - JarvisCAN V2</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem auto;max-width:52rem;padding:0 1rem;background:#0f1115;color:#e8e8e8}}
h1{{font-size:1.4rem}} li{{margin:1rem 0}} audio{{width:100%;max-width:32rem;margin-top:.35rem}}
code{{background:#1d212b;padding:.1rem .3rem;border-radius:.25rem}}
</style>
<h1>Muestras TTS - JarvisCAN</h1>
<p>Comparación de perfiles y voces de Piper. La página de voz principal usa el
puerto <code>8090</code>; esta página de muestras se sirve en <code>8092</code>.</p>
<ul>
{chr(10).join(rows)}
</ul>
</html>
"""
(out / "index.html").write_text(page, encoding="utf-8")
PY

if curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
  echo "Servidor de muestras ya activo en el puerto $PORT."
else
  nohup python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$DIR" >"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
  ok=0
  for _ in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 0.25
  done
  if [ "$ok" -ne 1 ]; then
    echo "No se pudo iniciar el servidor de muestras. Revisá $LOG" >&2
    exit 1
  fi
  echo "Servidor de muestras iniciado en el puerto $PORT."
fi

IP="$(ip_address)"
echo "Escuchá y compará: http://$IP:$PORT/"
echo "Para detenerlo: ./scripts/serve-tts-samples.sh --stop"
