#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
mkdir -p bin data
CC="${CC:-gcc}"
CFLAGS="${CFLAGS:--O2 -Wall -Wextra -std=c11}"
$CC $CFLAGS -o bin/can_logger src/can_logger.c src/obd.c src/db.c -lsqlite3 -lm
$CC $CFLAGS -o bin/can_query src/can_query.c -lsqlite3 -lm
$CC $CFLAGS -o bin/obd_ecu_sim tests/obd_ecu_sim.c
chmod +x scripts/simulate_can.py
echo "OK: bin/can_logger bin/can_query bin/obd_ecu_sim scripts/simulate_can.py"
