#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
DB="${JARVIS_CAN_DB:-$ROOT/data/vehicle.db}"
SIM_PID="$ROOT/data/can_simulator.pid"

if [ -f "$SIM_PID" ] && kill -0 "$(cat "$SIM_PID")" 2>/dev/null; then
    echo "Simulador Python: activo (PID $(cat "$SIM_PID"))"
else
    echo "Simulador Python: detenido"
fi
if [ -f "$DB" ]; then
    sqlite3 "$DB" "select 'muestras=' || count(*) from vehicle_samples;"
    echo "Últimas muestras:"
    sqlite3 -header -column "$DB" \
        "select ts_utc, source, round(speed_kph,1) as speed_kph,
                round(rpm,0) as rpm, round(coolant_c,1) as coolant_c,
                round(coolant_level_pct,0) as coolant_lvl,
                round(oil_level_pct,0) as oil_lvl,
                round(tire_fl_kpa,0) as tire_fl,
                dtc_codes, warning_flags
         from vehicle_samples order by epoch desc limit 5;"
else
    echo "DB: no existe todavía ($DB)"
fi
echo
"$ROOT/scripts/status-alerts.sh"
