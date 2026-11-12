#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
DB="${JARVIS_CAN_DB:-$ROOT/data/vehicle.db}"
INTERVAL="${CAN_SIM_INTERVAL:-60}"
DTC_EVERY="${CAN_SIM_DTC_EVERY:-10}"
PIDFILE="$ROOT/data/can_simulator.pid"
LOGFILE="$ROOT/data/can_simulator.log"

mkdir -p data
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "El simulador Python ya está activo (PID $(cat "$PIDFILE"))."
    exit 0
fi
rm -f "$PIDFILE" "$ROOT/data/can_simulator.sock" /tmp/jarvis-can-sim.sock
nohup python3 "$ROOT/scripts/simulate_can.py" \
    --db "$DB" --interval "$INTERVAL" --count 0 \
    --dtc-every "$DTC_EVERY" >"$LOGFILE" 2>&1 &
echo $! >"$PIDFILE"
sleep 0.5
if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "ERROR: el simulador Python no arrancó." >&2
    cat "$LOGFILE" >&2 || true
    exit 1
fi
echo "Simulador Python activo (PID $(cat "$PIDFILE")), cada ${INTERVAL}s."
echo "DTC forzado cada ${DTC_EVERY} muestras (0 = desactivado)."
echo "DB: $DB"
