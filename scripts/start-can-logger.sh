#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

IFACE="${CAN_IFACE:-can0}"
if [[ "$IFACE" != unix:* ]] && ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "ERROR: no existe la interfaz $IFACE."
    echo "Conecta un adaptador USB-CAN compatible con SocketCAN o usa la demo simulada."
    exit 2
fi

sudo -n systemctl start jarvis-can-logger
for _ in $(seq 1 20); do
    if systemctl is-active --quiet jarvis-can-logger; then
        break
    fi
    sleep 0.5
done

systemctl --no-pager --lines=0 status jarvis-can-logger || true
echo "Log: journalctl -u jarvis-can-logger -f"
