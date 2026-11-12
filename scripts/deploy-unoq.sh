#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "${BASH_SOURCE[0]}")"
ROOT="$(dirname "$SCRIPT")/.."
cd "$ROOT"

HOST="${UNOQ_HOST:-192.168.10.75}"
USER_NAME="${UNOQ_USER:-arduino}"
KEY="${UNOQ_KEY:-$HOME/.ssh/unoq_key}"
REMOTE="${UNOQ_DIR:-/home/arduino/JarvisCAN}"
SSH=(ssh -p 22 -i "$KEY" -o BatchMode=yes "$USER_NAME@$HOST")

"${SSH[@]}" "mkdir -p '$REMOTE'"
tar --exclude='.git' --exclude='bin' --exclude='models' --exclude='vendor' \
    --exclude='.pylibs' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='data/*.db' --exclude='data/*.db-*' --exclude='data/*.wav' \
    --exclude='data/*.log' --exclude='data/*.pid' --exclude='data/*.json' \
    --exclude='data/*.jsonl' -czf - . | "${SSH[@]}" "tar -xzf - -C '$REMOTE'"
"${SSH[@]}" "cd '$REMOTE' && chmod +x scripts/*.sh && ./scripts/build.sh"
"${SSH[@]}" "ln -sf '$REMOTE/scripts/start-all.sh' /home/arduino/start-can.sh && ln -sf '$REMOTE/scripts/stop-all.sh' /home/arduino/stop-can.sh && ln -sf '$REMOTE/scripts/status-all.sh' /home/arduino/status-can.sh"
echo "Desplegado en $USER_NAME@$HOST:$REMOTE"
echo "Control: ~/start-can.sh | ~/stop-can.sh | ~/status-can.sh"
echo "Servicio: sudo $REMOTE/scripts/install-service.sh"
