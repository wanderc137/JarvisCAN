#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta con sudo: sudo $0" >&2
    exit 1
fi

install -m 0644 systemd/jarvis-can-logger.service /etc/systemd/system/jarvis-can-logger.service
install -m 0440 config/sudoers-jarvis-can /etc/sudoers.d/90-jarvis-can
visudo -cf /etc/sudoers.d/90-jarvis-can
systemctl daemon-reload
systemctl enable jarvis-can-logger
echo "Servicio instalado y habilitado."
echo "Inicio: $ROOT/scripts/start-can-logger.sh"
echo "Parada: $ROOT/scripts/stop-can-logger.sh"
