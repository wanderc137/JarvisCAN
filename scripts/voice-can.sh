#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
export PYTHONPATH="$ROOT/.pylibs${PYTHONPATH:+:$PYTHONPATH}"
exec python3 scripts/voice-can.py "$@"
