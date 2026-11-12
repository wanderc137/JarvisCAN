#!/usr/bin/env bash
# run-service-sim.sh — arranque del simulador CAN bajo systemd.
# Escribe el PID file que usan status-can-demo.sh y el panel de alertas.
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
mkdir -p data
echo $$ > "$ROOT/data/can_simulator.pid"
exec /usr/bin/python3 "$ROOT/scripts/simulate_can.py" \
    --db "${JARVIS_CAN_DB:-$ROOT/data/vehicle.db}" \
    --interval "${CAN_SIM_INTERVAL:-60}" \
    --count 0 \
    --dtc-every "${CAN_SIM_DTC_EVERY:-10}"
