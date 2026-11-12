#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

TEXT="${1:-Se encontraron veinte registros de velocidad en la última hora. El más reciente es treinta y uno kilómetros por hora.}"
OUT="$ROOT/data/tts-samples"
mkdir -p "$OUT"

VOICES=(es_MX-claude-high es_ES-davefx-medium)
if [ "${TTS_COMPARE_ALL:-0}" = "1" ]; then
    VOICES+=(es_AR-daniela-high)
fi

run_sample() {
    local voice="$1"
    local label="$2"
    shift 2
    local model="$ROOT/models/piper/${voice}.onnx"
    if [ ! -f "$model" ]; then
        echo "AVISO: falta $model; se omite." >&2
        return 0
    fi
    local start end
    start="$(date +%s.%N)"
    if ! ./scripts/voice-can.sh --tts-test "$TEXT" --tts-model "$model" \
        --play-audio off "$@" >/dev/null 2>/tmp/tts-compare.err; then
        echo "ERROR: $voice $label" >&2
        cat /tmp/tts-compare.err >&2 || true
        return 1
    fi
    end="$(date +%s.%N)"
    python3 - "$voice" "$label" "$start" "$end" <<'PY'
import sys, wave
voice, label, start, end = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
with wave.open("data/last_answer.wav", "rb") as w:
    audio = w.getnframes() / w.getframerate()
print(f"{voice:20s} {label:10s} wall={end-start:5.2f}s audio={audio:5.2f}s")
PY
    cp data/last_answer.wav "$OUT/${voice}_${label}.wav"
}

for voice in "${VOICES[@]}"; do
    run_sample "$voice" flat --tts-profile flat
    run_sample "$voice" human --tts-profile human
    run_sample "$voice" human-lite --tts-profile human-lite
done

echo "Muestras en $OUT"
echo "Para escucharlas: ./scripts/serve-tts-samples.sh"
