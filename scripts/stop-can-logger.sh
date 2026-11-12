#!/usr/bin/env bash
set -euo pipefail
if sudo -n systemctl stop jarvis-can-logger; then
    echo "Servicio jarvis-can-logger detenido."
else
    echo "No se pudo detener el servicio. Revisa permisos sudo." >&2
    exit 1
fi
if systemctl is-active --quiet jarvis-can-logger; then
    echo "ERROR: el servicio sigue activo." >&2
    exit 1
fi
