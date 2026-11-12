#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

WITH_OLLAMA=1
WITH_WARMUP=1
WITH_SIM=1
WITH_ALERTS=1
WITH_TTS=1

usage() {
    cat <<'EOF'
Uso: start-all.sh [opciones]

Arranca todo JarvisCAN en orden:
  1. Ollama (servicio systemd)
  2. simulador CAN (una muestra cada 60 s)
  3. monitores de reglas y alertas por voz
  4. panel de alertas web (:8090)
  5. precarga del modelo LLM

Opciones:
  --no-ollama   No inicia Ollama (y omite la precarga)
  --no-warmup   No precarga el modelo
  --no-sim      No inicia el simulador
  --no-alerts   No inicia los monitores de alertas
  --no-tts      No inicia el panel de alertas web
  -h, --help    Muestra esta ayuda
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --no-ollama) WITH_OLLAMA=0 ;;
        --no-warmup) WITH_WARMUP=0 ;;
        --no-sim) WITH_SIM=0 ;;
        --no-alerts) WITH_ALERTS=0 ;;
        --no-tts) WITH_TTS=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Opción desconocida: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

echo "== JarvisCAN: arranque completo =="

if [ "$WITH_OLLAMA" = "1" ]; then
    if systemctl is-active --quiet ollama; then
        echo "Ollama: ya estaba activo."
    else
        if sudo -n systemctl start ollama 2>/dev/null; then
            echo "Ollama: iniciado."
        else
            echo "ERROR: no se pudo iniciar ollama (revisá sudoers)." >&2
            exit 1
        fi
    fi

    ok=0
    for _ in $(seq 1 60); do
        if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            ok=1
            break
        fi
        sleep 1
    done
    if [ "$ok" -ne 1 ]; then
        echo "ERROR: Ollama no responde en 127.0.0.1:11434." >&2
        exit 1
    fi
    echo "Ollama: API lista."
fi

if [ "$WITH_SIM" = "1" ]; then
    "$ROOT/scripts/start-can-sim.sh"
fi

if [ "$WITH_ALERTS" = "1" ]; then
    "$ROOT/scripts/start-alerts.sh"
fi

if [ "$WITH_TTS" = "1" ]; then
    "$ROOT/scripts/start-tts.sh"
fi

if [ "$WITH_OLLAMA" = "1" ] && [ "$WITH_WARMUP" = "1" ]; then
    MODEL="${JARVIS_CAN_MODEL:-${JARVIS_MODEL:-qwen2.5:0.5b-instruct-q4_K_M}}"
    echo "Modelo: precargando $MODEL..."
    if curl -fsS --max-time 180 http://127.0.0.1:11434/api/generate \
        -H 'Content-Type: application/json' \
        -d "{\"model\":\"$MODEL\",\"prompt\":\"hola\",\"stream\":false,\"keep_alive\":\"15m\",\"options\":{\"num_predict\":1}}" \
        >/dev/null 2>&1; then
        echo "Modelo: cargado."
    else
        echo "AVISO: no se pudo precargar el modelo; se cargará en la primera consulta." >&2
    fi
fi

echo
"$ROOT/scripts/status-all.sh" || true
echo
echo "JarvisCAN iniciado. Para detener: $ROOT/scripts/stop-all.sh"
