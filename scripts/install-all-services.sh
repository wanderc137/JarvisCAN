#!/usr/bin/env bash
# install-all-services.sh — instala y habilita los tres servicios de JarvisCAN:
#   jarvis-can-sim      simulador OBD-II (datos CAN ficticios)
#   jarvis-can-alerts   monitores de reglas + alertas por voz
#   jarvis-can-tts      panel web de alertas (:8090)
#
# Ejecutar como root:
#   sudo /home/arduino/JarvisCAN/scripts/install-all-services.sh
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

if [ "$(id -u)" -ne 0 ]; then
    echo "Ejecuta con sudo: sudo $0" >&2
    exit 1
fi

for unit in jarvis-can-sim jarvis-can-alerts jarvis-can-tts; do
    install -m 0644 "systemd/${unit}.service" "/etc/systemd/system/${unit}.service"
done

systemctl daemon-reload
systemctl enable --now jarvis-can-sim jarvis-can-alerts jarvis-can-tts

echo
for unit in jarvis-can-sim jarvis-can-alerts jarvis-can-tts; do
    printf '%-22s enabled=%s active=%s\n' \
        "$unit" \
        "$(systemctl is-enabled "$unit" 2>/dev/null || echo no)" \
        "$(systemctl is-active "$unit" 2>/dev/null || echo no)"
done
echo
echo "Panel de alertas: http://<IP-de-la-placa>:8090/"
echo "Logs: journalctl -u jarvis-can-sim -u jarvis-can-alerts -u jarvis-can-tts -f"
