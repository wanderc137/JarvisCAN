#!/usr/bin/env bash
# run-service-alerts.sh — monitores de alertas bajo systemd.
# Escribe el PID file que usa el panel (monitor_active) y status-alerts.sh.
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
mkdir -p data
echo $$ > "$ROOT/data/can_alerts.pid"
exec /usr/bin/python3 "$ROOT/scripts/can_alerts.py" \
    --db "${JARVIS_CAN_DB:-$ROOT/data/vehicle.db}" \
    --interval 180 \
    --initial-gap 300 \
    --play-audio auto
