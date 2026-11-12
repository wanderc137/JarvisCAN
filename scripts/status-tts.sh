#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
PORT="${TTS_PORT:-8090}"
IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
[ -n "$IP" ] || IP="$(hostname -I | awk '{print $1}')"

if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
  echo "Panel de alertas: ACTIVO en el puerto $PORT"
  echo "Panel en el navegador: http://$IP:$PORT/"
else
  echo "Panel de alertas: DETENIDO"
fi

if [ -f "$ROOT/data/last_answer.json" ]; then
  echo -n "Última respuesta: "
  python3 - <<PY
import json
from pathlib import Path
p = Path("$ROOT/data/last_answer.json")
try:
    d = json.loads(p.read_text(encoding="utf-8"))
    print(d.get("text", "")[:300])
except Exception:
    print("(ilegible)")
PY
else
  echo "Última respuesta: (todavía no hay)"
fi

if [ -f "$ROOT/data/alerts.jsonl" ]; then
  echo -n "Última alerta: "
  python3 - <<PY
import json
from pathlib import Path
p = Path("$ROOT/data/alerts.jsonl")
try:
    lines = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    d = json.loads(lines[-1]) if lines else {}
    print(f"{d.get('rule','')}: {d.get('message','')}"[:300])
except Exception:
    print("(ilegible)")
PY
fi
