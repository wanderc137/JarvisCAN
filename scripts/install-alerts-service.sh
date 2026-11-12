#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"
if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta con sudo: sudo $0" >&2
    exit 1
fi
install -m 0644 systemd/jarvis-can-alerts.service /etc/systemd/system/jarvis-can-alerts.service
systemctl daemon-reload
systemctl enable --now jarvis-can-alerts
echo "Servicio jarvis-can-alerts instalado, habilitado y activo."
echo "Estado: systemctl status jarvis-can-alerts"
echo "Log: journalctl -u jarvis-can-alerts -f"
