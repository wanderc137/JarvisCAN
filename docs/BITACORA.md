# Bitácora de JarvisCAN

Registro de decisiones, pruebas y caminos descartados. La intención es que
quien retome el proyecto no repita los mismos intentos.

## 1. Objetivo

Tener un sistema **offline** que:

1. obtenga datos OBD-II/CAN del Nissan Versa 2020;
2. los guarde como un registro por muestra en una única tabla SQLite;
3. reciba una pregunta en lenguaje natural;
4. la traduzca a parámetros de consulta;
5. consulte SQLite con un programa en C;
6. devuelva una tabla y un resumen;
7. opcionalmente responda por voz.

Todo debe resolverse en la UNO Q, sin servicios online.

## 2. Hardware y primeras decisiones

- La UNO Q tiene un MPU Linux (Qualcomm QRB2210, aarch64) y un MCU STM32U585
  con Zephyr.
- El Linux **no expone `can0`**; `ip link` solo muestra `lo`, `docker0` y
  `wlan0`.
- El STM32U585 tiene FDCAN1 en D4/D5, pero son señales lógicas de 3,3 V, no
  CANH/CANL.
- El core Arduino/Zephyr actual no expone CAN como periférico estándar.
- El kernel no permite `vcan` (`modprobe vcan` falla).

Conclusión: para CAN real hace falta un adaptador USB-CAN con host USB o un
transceptor CAN más firmware Zephyr. Mientras tanto se usa un simulador.

## 3. Programa C y SQLite

- `can_logger` lee SocketCAN, pide PIDs OBD-II y guarda una fila por muestra.
- `can_query` recibe los parámetros y construye SQL con una lista blanca de
  métricas y agregaciones.
- La tabla única `vehicle_samples` tiene 19 columnas `REAL`, `raw_json`,
  `ts_utc`, `epoch`, `source` y `pid_count`.
- Se activó WAL y `synchronous=NORMAL`; `can_query` abre en solo lectura.

## 4. Simulador

- `scripts/simulate_can.py` simula una ECU OBD-II con un ciclo de conducción
  de 300 s: ralentí, aceleración, crucero, desaceleración y frenada.
- Codifica las respuestas como tramas OBD-II ficticias, las decodifica y las
  inserta directamente en SQLite.
- No necesita hardware CAN.
- Se descartó el simulador C anterior (`can_simulator.c` y scripts asociados)
  cuando el usuario pidió un programa Python para generar los datos.

## 5. Asistente en lenguaje natural

- `scripts/jarvis-can-ask.py` usa Ollama para obtener
  `{metric, agg, from, to, limit, order}`.
- Se agregó `apply_question_hints()` para corregir casos en los que el modelo
  devolvía `agg=none` o `from=-60s`.
- El resumen final es determinista: se arma con los valores exactos de
  SQLite. El modelo no inventa cifras.
- El modelo por defecto es `qwen2.5:0.5b-instruct-q4_K_M`. El 1.5B queda
  disponible para más calidad, pero es más lento.

## 6. Voz: intentos y descartes

### AirPods

- Se intentó usar un manos libre UGREEN; el pareo falló.
- Se descartó el JBL Charge 4 por no tener micrófono.
- Se emparejaron unos AirPods (MAC omitida).
- La salida A2DP funcionó (se escuchó un tono).
- El micrófono HFP entregó **silencio absoluto** en mSBC y CVSD.
- Se probaron las dos sesiones de PipeWire (lightdm uid 103 y arduino uid
  1000), la fuente loopback, la fuente interna, reconexiones y reinicios.
- El micrófono de los AirPods no es utilizable en esta placa.
- Decisión: eliminar los AirPods. No se usan.

### Micrófono interno

- La tarjeta `ArduinoImolaHPH` tiene `DMIC1_MIXER`, `DMIC2_MIXER`, `ADC1` y
  `Mic Jack` en `off`.
- Se activaron los controles y se probaron `hw:0,0` a `hw:0,3`.
- Resultado: silencio, `Invalid argument`, `Device or resource busy` o
  `Input/output error`.
- Decisión: no usar el micrófono interno.

### Salida de audio de la placa

- `aplay -D plughw:0,0` falla con `Input/output error`.
- `pw-cat --playback` se cuelga; `pw-top` muestra `QUANT 0`, `RATE 0`.
- Se activaron `EAR_RDAC`, `HPHL/HPHR`, `HPHL_RDAC/HPHR_RDAC`, `LO_RDAC`,
  `RX_EAR` y `RX_HPH`; el error persiste.
- Decisión: la respuesta se reproduce en el teléfono o en la PC.

### IP Webcam

- El teléfono expone `http://192.168.1.198:8080/audio.wav`.
- Formato: WAV 44.100 Hz, mono, 16 bits, con señal real.
- `voice-can.py` lo remuestrea a 16 kHz y normaliza la ganancia.
- Funciona con Vosk.
- Prueba real: “¿cuál es la velocidad en la última hora?” → 20 registros,
  último 74 km/h.

## 7. TTS y página web

> **Histórico:** los botones Hablar/Activar voz y `POST /listen` corresponden a
> la etapa anterior. La página actual es el panel de alertas descrito más abajo.

- La primera versión usaba `espeak-ng`; sonaba robótica, como un sintetizador
  de los años 90.
- Se reemplazó por **Piper TTS**, con `espeak-ng` como respaldo.
- `voice-can.py` escribe `data/last_answer.wav` y `data/last_answer.json`.
- `tts-server.py` sirve la página en el puerto 8090.
- La página tiene **Hablar**, **Activar voz** y **Reproducir última
  respuesta**.
- `POST /listen` ejecuta `voice-can-cam.sh --auto --once --duration 8`.
- `GET /listen/status` informa el estado.
- La página reproduce el audio en el parlante del teléfono o de la PC.
- Se agregó el botón Hablar porque antes la página solo reproducía la última
  respuesta y no iniciaba una consulta nueva.

### Panel de alertas para usuario de prueba

- La página 8090 dejó de ser una página de voz con micrófono.
- Ahora es un **panel de alertas**: muestra la regla detectada, la hora y el
  mensaje, y reproduce el audio de cada alerta nueva.
- No usa STT ni micrófono; el usuario de prueba solo toca **Activar sonido** y
  deja la página abierta.
- `can_alerts.py` archiva cada WAV en `data/alert_audio/` (últimos 200) y
  registra `audio_file` en `data/alerts.jsonl`.
- El panel expone `/api/alerts` y `/alert-audio/<archivo>`.
- La entrada por voz por IP Webcam se conserva solo como utilidad de terminal.

### Piper TTS

- Se instaló el binario ARM64 de Piper `2023.11.14-2` en
  `vendor/piper/` (no versionado).
- La voz por defecto es `es_MX-claude-high`, en
  `models/piper/es_MX-claude-high.onnx` (no versionada).
- También quedaron disponibles `es_ES-davefx-medium` y
  `es_AR-daniela-high` para comparar.
- Pruebas de síntesis en la UNO Q:
  - `es_MX-claude-high`: 8,4 s para 7,8 s de audio.
  - `es_ES-davefx-medium`: 4,8 s para 6,1 s de audio.
  - `es_AR-daniela-high`: 23,7 s para 5,5 s de audio (demasiado lenta).
- Se eligió `es_MX-claude-high` por calidad y latencia razonable.
- `voice-can.py` usa `auto`: Piper si está instalado; si falla, espeak-ng.
- Se agregó `--tts-engine piper|espeak|auto`, `--tts-model`, `--piper-bin`,
  `--tts-length-scale` y `--tts-test`.
- Se agregó `scripts/install-piper.sh` para reproducir la instalación.
- Consulta completa en frío: 36 s (Ollama ~27 s + Piper ~8,6 s); en caliente
  baja.

## 8. Simulación con anomalías y alertas por voz

- Se amplió `vehicle_samples` con 6 columnas `REAL` (nivel de refrigerante,
  nivel de aceite y presión de los cuatro neumáticos) y 2 columnas `TEXT`
  (`dtc_codes`, `warning_flags`). El C y el simulador migran bases existentes
  con `ALTER TABLE`.
- El simulador genera tramas ficticias `0x600` (presiones), `0x601` (niveles),
  `0x602` (DTC en ASCII) y `0x603` (bitmask de warnings), además de las
  respuestas OBD-II normales.
- Cada 7 muestras se elige una anomalía al azar y se mantiene 5 muestras:
  refrigerante a 118 °C, nivel de refrigerante a 52 %, un neumático a 162 kPa,
  nivel de aceite a 48 %, dos DTC con warnings, o velocidad a 146 km/h.
- Se agregó `--dtc-every` al simulador: `start-can-sim.sh` usa 10 por
  defecto para garantizar un DTC periódico aunque la anomalía aleatoria no lo
  elija. La regla DTC ahora busca en una ventana de 20 muestras
  (`--dtc-window`), así no depende de que la última muestra tenga el código.
- `scripts/can_alerts.py` evalúa seis reglas: temperatura, nivel de
  refrigerante, presión de neumáticos, nivel de aceite, DTC/warnings y exceso
  de velocidad. Cada regla arranca con 5 minutos de desfase y luego se repite
  cada 3 minutos.
- El audio usa Piper vía `voice-can.sh --tts-test ... --play-audio auto`; si el
  EW02 Plus está conectado se reproduce ahí; si no, queda el WAV para la página
  TTS. El timestamp ISO no se pronuncia.
- Estado y registros: `data/alerts_state.json`, `data/alerts.log` y
  `data/alerts.jsonl`. `start-can-demo.sh` arranca simulador y monitores;
  `CAN_DEMO_ALERTS=0` permite arrancar solo el simulador.
- Prueba en `/tmp/jarvis_test.db` con `--anomaly all --anomaly-every 7`:
  las muestras 7–11 mostraron 118 °C, 52 %, 48 %, un neumático a 162 kPa,
  `P0128,U0100` y 146 km/h; las 12–13 volvieron a valores normales.
- Verificación en la placa: el simulador migró la base real y siguió
  insertando cada 60 s con las columnas nuevas (más de 320 muestras al
  2026-11-05 12:41 UTC); la muestra de 12:39:29 trajo `C0035,P0171` y
  `CHECK_ENGINE`. Una alerta de temperatura se generó y se reprodujo en el
  EW02 Plus (`played_on_device: true`), y el usuario confirmó que se escuchó
  bien. También se ejecutó la regla DTC contra la base real y el mensaje
  “Se han detectado códigos de falla: C0035, P0171; avisos: testigo de motor”
  se reprodujo en el EW02; el usuario confirmó que le llegó el mensaje de
  testigo de motor. El planificador se probó con offsets cortos y los respetó.
  A las 12:46:54 UTC la regla programada `coolant_level` disparó por una
  anomalía de 52 % y el log registró `audio OK en EW02 Plus`, validando el
  ciclo automático cada 3 minutos.
- Prueba de garantía DTC (2026-11-05 13:02 UTC): una base temporal generada
  con `--dtc-every 1` produjo `P0128, P0171`; la regla
  `--only dtc --once --play-audio on` detectó los códigos y reprodujo el audio
  en el EW02 Plus (`played_on_device: true`). El simulador en vivo quedó con
  `--dtc-every 10` (peor caso cada 20 muestras si coincide con otra anomalía).
- Los monitores quedaron activos con `start-alerts.sh`; el servicio systemd
  queda disponible pero no se habilitó para no duplicar procesos. El detalle
  de reglas está en `ALERTS.md`.

## 9. Control manual start/stop

> **Actualización 2026-11-11:** la demo pasó a tres servicios systemd
> habilitados (`jarvis-can-sim`, `jarvis-can-alerts`, `jarvis-can-tts`). El
> control manual sigue disponible para desarrollo. Ver sección 13.

- Se agregaron `scripts/start-all.sh`, `stop-all.sh` y `status-all.sh` para
  arrancar y detener todo JarvisCAN a pedido, sin habilitar unidades systemd
  nuevas.
- Orden de arranque: Ollama → espera `/api/tags` → simulador → alertas → TTS
  → precarga del modelo 0.5B. Orden de parada: alertas → simulador → TTS →
  Ollama; `--keep-ollama` deja el LLM activo.
- En la placa quedaron los atajos `~/start-can.sh`, `~/stop-can.sh` y
  `~/status-can.sh`.
- Prueba real: parada total y arranque total en 9 s; quedaron activos
  simulador, alertas, TTS, Ollama y el modelo cargado (~486 MB). `start-all.sh`
  es idempotente: si un proceso ya está activo, no lo duplica.
- Opciones: `--no-ollama`, `--no-warmup`, `--no-sim`, `--no-alerts`,
  `--no-tts`.

### Migración a la versión única (2026-11-05)

- Se eligió la V2 (voz `human-lite`) como versión definitiva. La V1 quedó
  retirada: se eliminó su carpeta local, su instalación en la placa y su
  contenido en GitHub.
- Antes de borrar se conservó la base más reciente de la V1 (436 muestras,
  última `2026-11-05T14:27:24Z`) y se copió a la V2.
- La carpeta canónica pasó a ser `JarvisCAN` en local y en la placa; el TTS
  quedó en el puerto **8090** y los atajos son `~/start-can.sh`,
  `~/stop-can.sh` y `~/status-can.sh`.
- El repositorio privado `wanderc137/JarvisCAN` se reemplazó con el contenido
  de la V2. Ya no hay dos servidores JarvisCAN ni dos bases en paralelo.
- Los servidores de rostros (`unoq-app` y `unoq-app-v2`) son proyectos
  separados y no se tocaron.

## 10. Estado actual

- Fecha de referencia: 2026-11-11.
- Versión única: **JarvisCAN 2.0**; la V1 fue eliminada.
- Proyecto local: `~/Documents/Proyects/OpenCode/AG.CreadorContenido/proyectos/JarvisCAN`.
- Placa: `/home/arduino/JarvisCAN`.
- Ollama activo con `qwen2.5:0.5b-instruct-q4_K_M`.
- TTS: Piper `es_MX-claude-high`, perfil `human-lite` por defecto; fallback
  `espeak-ng`.
- El simulador, los monitores de alertas y el panel corren como servicios
  systemd habilitados (`jarvis-can-sim`, `jarvis-can-alerts`,
  `jarvis-can-tts`) con `Restart=always`; arrancan solos con la placa. La base
  `data/vehicle.db` conserva las muestras generadas.
- Panel de alertas: `http://192.168.10.1:8090/` (vía router demo) o
  `http://192.168.10.75:8090/` (directo).
- Micrófono: IP Webcam solo para la utilidad de voz por terminal; el panel no lo usa.
- AirPods eliminados.
- Salida de audio de la UNO Q: no utilizable; el audio se reproduce en el
  navegador del visitante.
- EW02 Plus: salida verificada; micrófono no funciona.
- CAN real: pendiente de hardware (adaptador USB-CAN o transceptor + Zephyr).
- Repositorio Git: publicado privado en
  `https://github.com/wanderc137/JarvisCAN`.

## 11. Pendientes

1. Usar el EW02 Plus como salida (verificado). Su micrófono entrega
   silencio; falta un micrófono que funcione en Linux.
2. Conectar hardware CAN real y validar `can_logger` contra el bus del auto.
3. Evaluar un micrófono USB o un headset con micrófono que funcione en Linux.
4. Medir CPU/RAM/temperatura en sesiones largas.
5. Agregar autenticación al servidor TTS si se usa en una red no confiable.

## 12. Lecciones

- No dar por sentado que un headset Bluetooth funciona como micrófono en
  Linux; la salida A2DP puede andar y el HFP no.
- La UNO Q no tiene salida de audio utilizable sin hardware externo.
- IP Webcam es una solución práctica y offline para el micrófono.
- El resumen debe ser determinista para no inventar valores.
- La simulación no reemplaza una prueba con hardware CAN real.
- `espeak-ng` es robótico por diseño; Piper mejora la naturalidad sin salir
  de la placa, a costa de unos segundos de CPU por frase.

## 13. Demo simultánea, servicios y panel de feria (2026-11-11)

- Se limpió la instalación vieja de reconocimiento facial v1 para liberar
  recursos: servicio `unoq-app` eliminado, puerto 8000 cerrado y carpeta
  `/home/arduino/AnalizadorRostroUNOQ` borrada (257 MB). La v2 quedó intacta
  en el puerto 8001.
- JarvisCAN pasó de control manual a **tres servicios systemd** habilitados:
  `jarvis-can-sim`, `jarvis-can-alerts` y `jarvis-can-tts`, con
  `Restart=always`. Los wrappers `run-service-*.sh` escriben los PID files
  para que `status-*.sh` y el panel sigan funcionando.
- El router demo OpenWrt (`192.168.10.1`) publica el panel con DNAT:
  `http://192.168.10.1:8090/`. También se agregaron reglas SNAT de hairpin
  para que la URL funcione desde la misma LAN. La placa conserva su acceso
  directo en `http://192.168.10.75:8090/`.
- El panel se rediseñó para feria: hero con radar animado, seis tarjetas de
  reglas con umbrales y contadores, estado «En guardia»/«Disparó» con brillo
  de 8 s, feed con punto de color por regla y ecualizador animado.
- El audio de las alertas lo reproduce el **navegador del visitante**, no el
  Bluetooth de la placa. Se verificó con Playwright/Chromium: una alerta de
  presión de neumático generada en vivo se reprodujo completa (12,86 s) desde
  la URL del router después de tocar **Activar sonido**.
- Las cuatro unidades de la demo (rostros v2 + los tres servicios JarvisCAN)
  quedaron activas y habilitadas. No se reinició la placa para no cortar la
  demo; el autoarranque está garantizado por `systemctl enable`.
- El reloj de la placa no tiene NTP ni Internet y puede estar desfasado; las
  horas del panel pueden no coincidir con la hora real.
