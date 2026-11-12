#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
DB="${JARVIS_CAN_DB:-$ROOT/data/vehicle.db}"
INTERVAL="${CAN_SIM_INTERVAL:-60}"

"$ROOT/scripts/start-can-sim.sh"
if [ "${CAN_DEMO_ALERTS:-1}" = "1" ]; then
    "$ROOT/scripts/start-alerts.sh"
else
    echo "Alertas por voz desactivadas (CAN_DEMO_ALERTS=0)."
fi
echo "Demo CAN activa: el simulador Python inserta una muestra cada ${INTERVAL}s."
echo "Consultas: $ROOT/scripts/ask-can.sh \"¿Cuál fue la velocidad máxima en la última hora?\""
echo "Alertas: $ROOT/scripts/status-alerts.sh"
echo "Detener: $ROOT/scripts/stop-can-demo.sh"
