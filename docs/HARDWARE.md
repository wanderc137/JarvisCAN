# Hardware CAN en Arduino UNO Q

## Situación

La Arduino UNO Q combina un MPU Linux (Qualcomm QRB2210) y un MCU STM32U585 con Zephyr. El Linux no trae una interfaz CAN y el core Arduino actual no expone FDCAN como periférico estándar.

El STM32U585 sí tiene FDCAN1:

- `D4` = FDCAN1_TX (PA12)
- `D5` = FDCAN1_RX (PA11)

Son señales lógicas de 3,3 V. **No son CANH/CANL** y no se pueden conectar directamente al bus del auto.

## Opción A: adaptador USB-CAN

Es la ruta más simple desde Linux:

1. Adaptador USB-CAN con soporte SocketCAN (por ejemplo, MCP2515 por SPI o un adaptador USB genérico compatible).
2. La UNO Q necesita actuar como host USB. Su único USB-C es de alimentación y datos; para host hace falta:
   - hub USB-C con entrada **Power Delivery** (fuente PD al hub, hub a la UNO Q, adaptador CAN a un puerto USB-A), o
   - alimentación por VIN (7–24 V) y puente en **JCTL** para forzar host mode, con adaptador USB-C OTG.
3. Verificar:

```bash
lsusb
ip -details link show can0
candump can0
```

## Opción B: transceptor + puente MCU

1. Transceptor CAN 3,3 V (SN65HVD230, TJA1051/3, etc.).
2. `D4` (TX) y `D5` (RX) al transceptor; CANH/CANL al bus del auto; alimentación y masa comunes.
3. Firmware Zephyr en el STM32U585 que configure FDCAN1 y reenvíe tramas al Linux (`/dev/ttyHS1` o RPC).
4. En Linux, un puente que reciba esas tramas y las publique en una interfaz SocketCAN o en el socket del simulador.

Esta opción requiere desarrollo de firmware y no está implementada en este repositorio.

## Opción C: simulación en Python

`scripts/simulate_can.py` simula la ECU OBD-II, codifica y decodifica las respuestas como tramas CAN ficticias y las inserta directamente en SQLite:

```text
simulate_can.py  --tramas OBD-II ficticias-->  vehicle_samples
```

Se usa porque el kernel de la UNO Q no incluye el módulo `vcan` y no hay hardware CAN conectado. No requiere hardware y permite validar el esquema SQLite, `can_query` y el asistente en lenguaje natural. No sustituye una prueba con transceptor real.

## Advertencias

- No conectar D4/D5 al bus CAN directamente.
- Usar un transceptor aislado o, como mínimo, una puesta a masa común y protección.
- No alimentar la UNO Q y el adaptador desde fuentes que creen lazos de masa.
- Con el motor en marcha hay ruido eléctrico; usar cable trenzado y terminación de 120 Ω en los extremos del bus.
- Verificar la tensión del bus del Versa (CAN de 5 V o 3,3 V según transceptor) antes de conectar.
