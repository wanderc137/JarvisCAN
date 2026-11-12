#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
PIDFILE="$ROOT/data/can_alerts.pid"
DB="${JARVIS_CAN_DB:-$ROOT/data/vehicle.db}"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    PID="$(cat "$PIDFILE")"
    echo "Monitores de alertas: activos (PID $PID)"
    ps -o pid,etime,%cpu,rss,args -p "$PID" || true
else
    echo "Monitores de alertas: detenidos"
fi
echo
echo "== reglas =="
python3 scripts/can_alerts.py --list-rules || true
echo
echo "== estado =="
if [ -f data/alerts_state.json ]; then
    python3 - <<'PY'
import json
from pathlib import Path
p = Path('data/alerts_state.json')
d = json.loads(p.read_text(encoding='utf-8'))
print('dtc_seen:', ','.join(d.get('dtc_seen', [])) or '-')
print('warning_seen:', ','.join(d.get('warning_seen', [])) or '-')
print('overspeed_active:', d.get('overspeed_active', False))
print('last_alerts:', json.dumps(d.get('last_alerts', {}), ensure_ascii=False))
PY
else
    echo "sin estado todavía"
fi
echo
echo "== últimas muestras =="
if [ -f "$DB" ]; then
    sqlite3 -header -column "$DB" \
        "select ts_utc, round(speed_kph,1) speed, round(coolant_c,1) coolant,
                round(coolant_level_pct,0) coolant_lvl, round(oil_level_pct,0) oil_lvl,
                round(tire_fl_kpa,0) tire_fl, dtc_codes, warning_flags
         from vehicle_samples order by epoch desc limit 3;" || true
else
    echo "sin base en $DB"
fi
echo
echo "== últimas alertas =="
if [ -f data/alerts.log ]; then
    tail -n 8 data/alerts.log
else
    echo "sin alertas registradas"
fi
