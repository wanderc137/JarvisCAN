#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIPER_VERSION="${PIPER_VERSION:-2023.11.14-2}"
VOICE="${PIPER_VOICE:-es_MX-claude-high}"
FORCE=false

usage() {
  cat <<EOF
Uso: $0 [--voice NOMBRE] [--force]

Instala Piper TTS y una voz en español dentro del proyecto.

Voces soportadas:
  es_MX-claude-high     (default, latinoamericana, alta calidad)
  es_ES-davefx-medium   (España, media)
  es_AR-daniela-high    (Argentina, alta calidad, más lenta)

Variables:
  PIPER_VERSION   versión del release (default $PIPER_VERSION)
  PIPER_VOICE     voz por defecto (default $VOICE)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --voice)
      [ $# -ge 2 ] || { echo "Falta el nombre de la voz" >&2; exit 2; }
      VOICE="$2"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opción desconocida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$VOICE" in
  es_MX-claude-high)   SUBDIR="es/es_MX/claude/high" ;;
  es_ES-davefx-medium) SUBDIR="es/es_ES/davefx/medium" ;;
  es_AR-daniela-high)  SUBDIR="es/es_AR/daniela/high" ;;
  *)
    echo "Voz no soportada: $VOICE" >&2
    usage >&2
    exit 2
    ;;
esac

case "$(uname -m)" in
  aarch64|arm64) ASSET="piper_linux_aarch64.tar.gz" ;;
  armv7l)        ASSET="piper_linux_armv7l.tar.gz" ;;
  x86_64|amd64)  ASSET="piper_linux_x86_64.tar.gz" ;;
  *)
    echo "Arquitectura no soportada: $(uname -m)" >&2
    exit 2
    ;;
esac

TMP="$(mktemp -d "${TMPDIR:-/tmp}/piper-install.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

VENDOR="$ROOT/vendor/piper"
MODEL_DIR="$ROOT/models/piper"
MODEL_ONNX="$MODEL_DIR/$VOICE.onnx"
MODEL_JSON="$MODEL_DIR/$VOICE.onnx.json"
RELEASE_URL="https://github.com/rhasspy/piper/releases/download/$PIPER_VERSION/$ASSET"
MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/$SUBDIR/$VOICE.onnx"

mkdir -p "$ROOT/vendor" "$MODEL_DIR"

if [ "$FORCE" = true ] || [ ! -x "$VENDOR/piper" ]; then
  echo "Descargando Piper $PIPER_VERSION ($ASSET)..."
  curl -fL --retry 3 -o "$TMP/piper.tar.gz" "$RELEASE_URL"
  if [ "$FORCE" = true ] && [ -d "$VENDOR" ]; then
    rm -rf "$VENDOR"
  fi
  tar -xzf "$TMP/piper.tar.gz" -C "$ROOT/vendor"
else
  echo "Piper ya está instalado en $VENDOR"
fi

if [ "$FORCE" = true ] || [ ! -f "$MODEL_ONNX" ]; then
  echo "Descargando voz $VOICE..."
  curl -fL --retry 3 -o "$TMP/$VOICE.onnx" "$MODEL_URL"
  curl -fL --retry 3 -o "$TMP/$VOICE.onnx.json" "$MODEL_URL.json"
  mv "$TMP/$VOICE.onnx" "$MODEL_ONNX"
  mv "$TMP/$VOICE.onnx.json" "$MODEL_JSON"
else
  echo "Modelo ya presente: $MODEL_ONNX"
fi

if [ ! -x "$VENDOR/piper" ]; then
  echo "Error: no se encontró $VENDOR/piper" >&2
  exit 1
fi

LD_LIBRARY_PATH="$VENDOR" "$VENDOR/piper" --help >/dev/null 2>&1

echo
echo "Piper instalado: $VENDOR"
echo "Voz instalada:   $MODEL_ONNX"
echo "Prueba:          ./scripts/voice-can.sh --tts-test \"Hola, soy Jarvis.\""
