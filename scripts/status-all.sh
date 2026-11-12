#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

echo "== JarvisCAN: estado general =="
if systemctl is-active --quiet ollama; then
    echo "Ollama: ACTIVO"
    TAGS="$(curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null || true)"
    if [ -n "$TAGS" ]; then
        printf '%s' "$TAGS" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Modelos: " + (", ".join(m.get("name","?") for m in d.get("models", [])) or "(ninguno)"))' 2>/dev/null || echo "Modelos: (no se pudo leer /api/tags)"
    else
        echo "API Ollama: sin respuesta"
    fi
else
    echo "Ollama: DETENIDO"
fi

echo
"$ROOT/scripts/status-can-demo.sh" || true
echo
"$ROOT/scripts/status-tts.sh" || true
