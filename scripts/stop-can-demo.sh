#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
"$ROOT/scripts/stop-alerts.sh"
"$ROOT/scripts/stop-can-sim.sh"
echo "Demo CAN detenida."
