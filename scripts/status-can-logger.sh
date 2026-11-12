#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

echo "== servicio =="
systemctl --no-pager --lines=0 status jarvis-can-logger || true
echo
echo "== interfaz =="
ip -details link show can0 2>/dev/null || echo "can0 no disponible"
echo
echo "== base =="
ls -lh data/vehicle.db* 2>/dev/null || echo "sin base"
echo
if [ -x bin/can_query ]; then
    echo "== ultimas muestras =="
    bin/can_query --db data/vehicle.db --last 5 --limit 5 --format table || true
fi
echo
echo "== CPU/RAM =="
ps -eo pid,comm,%cpu,rss,args | grep -E 'can_logger|PID' | grep -v grep || true
free -h
