#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
PIDFILE="$ROOT/data/can_alerts.pid"
LOG="$ROOT/data/can_alerts.log"
mkdir -p data
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "Los monitores de alertas ya están activos (PID $(cat "$PIDFILE"))."
    exit 0
fi
rm -f "$PIDFILE"
nohup python3 "$ROOT/scripts/can_alerts.py" "$@" >"$LOG" 2>&1 &
echo $! >"$PIDFILE"
sleep 0.5
if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "ERROR: los monitores no arrancaron." >&2
    cat "$LOG" >&2 || true
    rm -f "$PIDFILE"
    exit 1
fi
echo "Monitores de alertas activos (PID $(cat "$PIDFILE"))."
echo "Log: $LOG"
echo "Reglas: $ROOT/scripts/can_alerts.py --list-rules"
