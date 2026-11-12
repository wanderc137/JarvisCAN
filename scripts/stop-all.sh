#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

STOP_OLLAMA=1

usage() {
    cat <<'EOF'
Uso: stop-all.sh [opciones]

Detiene todo JarvisCAN en orden:
  1. monitores de alertas
  2. simulador CAN
  3. servidor TTS
  4. Ollama

Opciones:
  --keep-ollama  Deja Ollama activo
  -h, --help     Muestra esta ayuda
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --keep-ollama) STOP_OLLAMA=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

echo "== JarvisCAN: parada completa =="
"$ROOT/scripts/stop-alerts.sh" || true
"$ROOT/scripts/stop-can-sim.sh" || true
"$ROOT/scripts/stop-tts.sh" || true

if [ "$STOP_OLLAMA" = "1" ]; then
    if systemctl is-active --quiet ollama; then
        if sudo -n systemctl stop ollama 2>/dev/null; then
            echo "Ollama: detenido."
        else
            echo "AVISO: no se pudo detener Ollama (revisá sudoers)." >&2
        fi
    else
        echo "Ollama: ya estaba detenido."
    fi
else
    echo "Ollama: se deja activo (--keep-ollama)."
fi

echo "JarvisCAN detenido."
