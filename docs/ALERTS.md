# Alertas por voz sobre datos CAN simulados

Este documento describe el simulador de anomalías y los monitores que generan
avisos hablados a partir de la tabla `vehicle_samples`. Todo funciona offline
en la UNO Q; no se consulta ningún servicio de internet.

> **Alcance actual:** la UNO Q no tiene una interfaz CAN real (`can0`). El
> simulador Python inserta muestras ficticias directamente en SQLite para
> probar las reglas y el audio. El programa C `can_logger` queda preparado para
> un adaptador USB-CAN o un puente desde el MCU, pero no se ejecuta sin `can0`.

## Componentes

| Componente | Función |
|---|---|
| `scripts/simulate_can.py` | Simula la ECU OBD-II, genera anomalías aleatorias y escribe una muestra por minuto en SQLite. |
| `scripts/can_alerts.py` | Evalúa las 6 reglas, genera el audio con Piper, lo archiva y lo reproduce en el audífono Bluetooth si está conectado. |
| `scripts/tts-server.py` | Panel web de alertas (texto + audio) en el puerto 8090. |
| `scripts/start-alerts.sh` / `stop-alerts.sh` / `status-alerts.sh` | Arranque, parada y estado de los monitores. |
| `scripts/start-can-demo.sh` / `stop-can-demo.sh` | Arrancan o detienen simulador + monitores. |
| `scripts/start-all.sh` / `stop-all.sh` | Arranque/parada manual de todo el sistema (Ollama, simulador, alertas, TTS). |
| `systemd/jarvis-can-alerts.service` | Variante persistente para systemd. |
| `data/alerts.log` / `data/alerts.jsonl` | Registro legible y registro estructurado de cada alerta. |
| `data/alerts_state.json` | Estado de DTC/warnings vistos y de exceso de velocidad. |

## Columnas nuevas de `vehicle_samples`

Además de las 19 métricas OBD-II originales, la tabla acepta:

| Columna | Unidad | Origen simulado |
|---|---|---|
| `coolant_level_pct` | % | Trama ficticia `0x601` |
| `oil_level_pct` | % | Trama ficticia `0x601` |
| `tire_fl_kpa` | kPa | Trama ficticia `0x600` (delantero izquierdo) |
| `tire_fr_kpa` | kPa | Trama ficticia `0x600` (delantero derecho) |
| `tire_rl_kpa` | kPa | Trama ficticia `0x600` (trasero izquierdo) |
| `tire_rr_kpa` | kPa | Trama ficticia `0x600` (trasero derecho) |
| `dtc_codes` | texto | Trama ficticia `0x602`, códigos separados por coma |
| `warning_flags` | texto | Trama ficticia `0x603`, avisos separados por coma |

El simulador y el logger C migran bases existentes con `ALTER TABLE` al
arrancar. La consulta C `can_query` ya expone estas columnas como métricas.

## Simulador de anomalías

Por defecto, cada **7 muestras** (7 minutos con `--interval 60`) el simulador
elige al azar un tipo de anomalía y la mantiene **5 muestras**:

| Tipo | Efecto |
|---|---|
| `engine_temp` | Refrigerante a 118 °C y aceite a 112 °C; warning `HIGH_COOLANT_TEMP`. |
| `coolant_level` | Nivel de refrigerante a 52 %; warning `LOW_COOLANT`. |
| `tire_pressure` | Un neumático baja a 162 kPa; warning `LOW_TIRE_PRESSURE`. |
| `oil_level` | Nivel de aceite a 48 %; warning `LOW_OIL`. |
| `dtc` | Dos códigos de falla y warnings de motor. |
| `overspeed` | Velocidad 146 km/h, RPM 3900 y acelerador 65 %; warning `OVERSPEED`. |

Además, `scripts/start-can-sim.sh` intenta forzar un DTC cada **10 muestras**
(`CAN_SIM_DTC_EVERY=10`) para garantizar que la regla DTC reciba eventos
aunque la anomalía aleatoria no elija esa opción. Si en ese momento hay otra
anomalía activa, el DTC se pospone; en el peor caso aparece cada 20 muestras.
`CAN_SIM_DTC_EVERY=0` lo desactiva.

Opciones útiles:

```bash
# Anomalías aleatorias cada 7 muestras (default)
python3 scripts/simulate_can.py --interval 60 --count 0

# Forzar todas las anomalías en cada ventana
python3 scripts/simulate_can.py --anomaly all --anomaly-every 7

# Sin anomalías
python3 scripts/simulate_can.py --anomaly none

# Una anomalía concreta
python3 scripts/simulate_can.py --anomaly tire_pressure

# Forzar un DTC cada 10 muestras, además de las anomalías aleatorias
python3 scripts/simulate_can.py --dtc-every 10

# Solo DTC, sin otras anomalías
python3 scripts/simulate_can.py --anomaly dtc --anomaly-every 10
```

## Reglas y umbrales

Cada regla lee la última muestra y una ventana de hasta 10 muestras previas
para la media móvil. Los umbrales se pueden cambiar por CLI o en el servicio.

| Regla | Condición | Mensaje hablado |
|---|---|---|
| `engine_temp` | `coolant_c >= 105` °C **o** 15 °C por encima de la media móvil | “Se ha detectado un valor de temperatura riesgoso, medido en X grados Celsius. La media móvil previa era Y grados.” |
| `coolant_level` | `coolant_level_pct <= 60` % | “Se ha detectado un nivel de refrigerante riesgoso, medido en X por ciento, igual o menor al 60 por ciento.” |
| `tire_pressure` | Algún neumático `<= 180` kPa **o** 25 % por debajo de su media móvil | “Se ha detectado una caída de presión en el neumático [posición], medida en X kilopascales. La media móvil previa era Y kilopascales.” |
| `oil_level` | `oil_level_pct <= 60` % | “Se ha detectado un nivel de aceite riesgoso, medido en X por ciento, igual o menor al 60 por ciento.” |
| `dtc` | Aparecen códigos DTC o warnings nuevos en las últimas 20 muestras | “Se han detectado códigos de falla: ...; avisos: ...” |
| `overspeed` | `speed_kph > 130` km/h | “Se ha detectado exceso de velocidad, medido en X kilómetros por hora, superior a 130.” |

La regla `dtc` no mira solo la última muestra: busca en las últimas
`--dtc-window` muestras (20 por defecto) para no perder un código que haya
aparecido entre dos chequeos. Los warnings se traducen al hablar
(`CHECK_ENGINE` → “testigo de motor”,
`LOW_COOLANT` → “nivel bajo de refrigerante”, etc.). Los códigos DTC se leen
tal cual.

### Desfase entre reglas

El monitor arranca las reglas con un desfase de **5 minutos** y luego cada una
se repite cada **3 minutos**:

| Regla | Primera evaluación |
|---|---:|
| `engine_temp` | 0 min |
| `coolant_level` | 5 min |
| `tire_pressure` | 10 min |
| `oil_level` | 15 min |
| `dtc` | 20 min |
| `overspeed` | 25 min |

Así se evita que varias reglas hablen al mismo tiempo. Si dos reglas coinciden
por demora, `--audio-gap` agrega una pausa entre audios de la misma regla.

## Audio

`can_alerts.py` ejecuta:

```bash
scripts/voice-can.sh --tts-test "<mensaje>" --play-audio auto
```

- Piper sintetiza la voz (`es_MX-claude-high`, perfil `human-lite` por defecto).
- Cada audio se copia a `data/alert_audio/alert_<timestamp>_<regla>.wav`.
  Se conservan los últimos 200 WAV (`--alert-audio-keep`).
- `data/alerts.jsonl` incluye `audio_file`; el panel lo usa para servir el WAV.
- Si el audífono Bluetooth EW02 Plus está conectado, reproduce ahí. Si no,
  el panel web (`http://192.168.10.1:8090/` vía router demo o
  `http://192.168.10.75:8090/` directo) lo reproduce en el teléfono o PC.
- El timestamp ISO no se pronuncia; solo queda en el texto.
- `--play-audio off` genera el audio sin reproducirlo.
- `--no-audio` desactiva por completo la síntesis.

## Panel web de alertas

`scripts/tts-server.py` sirve el panel en el puerto **8090**, pensado para una
demo de feria donde la página queda abierta durante horas:

- muestra la última alerta con **regla**, hora y **mensaje**;
- muestra las **6 reglas configuradas** en tarjetas con umbrales, contador de
  alertas y última hora;
- al dispararse una regla, su tarjeta brilla 8 segundos y pasa de «En guardia»
  a «Disparó»;
- muestra un feed de alertas recientes con punto de color por regla;
- reproduce automáticamente cada alerta nueva después de tocar
  **Activar sonido**;
- no captura micrófono ni usa STT;
- no reproduce el historial al abrir la página.

Acceso:

| Vía | URL |
|---|---|
| Router demo | **http://192.168.10.1:8090/** |
| Directo a la placa | http://192.168.10.75:8090/ |

API:

| Método | Ruta | Función |
|---|---|---|
| GET | `/` | Panel de alertas |
| GET | `/api/alerts?limit=60` | Alertas recientes y `monitor_active` |
| GET | `/alert-audio/<archivo>` | WAV archivado de una alerta |
| GET | `/answer.wav` | Último WAV generado (compatibilidad) |
| GET | `/healthz` | Estado del panel |

Para levantarlo:

```bash
./scripts/start-tts.sh
# o
./scripts/start-all.sh
```

## Uso

En la demo, los tres servicios ya están activos; los comandos manuales son
para desarrollo y pruebas.

```bash
cd ~/JarvisCAN

# Sistema completo, a mano
./scripts/start-all.sh
./scripts/status-all.sh
./scripts/stop-all.sh

# Alternativa: solo simulador + monitores
./scripts/start-can-demo.sh
./scripts/status-can-demo.sh
./scripts/status-alerts.sh
./scripts/stop-can-demo.sh

# Solo monitores
./scripts/start-alerts.sh
./scripts/start-alerts.sh --interval 180 --initial-gap 300 --play-audio auto

# Prueba única, sin audio, contra la base actual
python3 scripts/can_alerts.py --once --dry-run

# Probar solo temperatura y hablar por el audífono
python3 scripts/can_alerts.py --only engine_temp --once --play-audio on

# Elegir otra base de prueba
python3 scripts/can_alerts.py --db /tmp/jarvis_test.db --once --dry-run
```

### Variables de entorno

| Variable | Uso |
|---|---|
| `JARVIS_CAN_DB` | Ruta alternativa de la base. |
| `CAN_SIM_INTERVAL` | Intervalo del simulador (default 60 s). |
| `CAN_DEMO_ALERTS=0` | `start-can-demo.sh` no arranca los monitores. |

## Servicios systemd (autoarranque)

La demo usa tres unidades habilitadas con `Restart=always`:

| Unidad | Función |
|---|---|
| `jarvis-can-sim` | Simulador OBD-II; inserta una muestra cada 60 s |
| `jarvis-can-alerts` | Monitores de 6 reglas + TTS cada 180 s |
| `jarvis-can-tts` | Panel web de alertas en `0.0.0.0:8090` |

Instalación o reinstalación completa:

```bash
sudo ./scripts/install-all-services.sh
systemctl is-enabled jarvis-can-sim jarvis-can-alerts jarvis-can-tts
systemctl is-active jarvis-can-sim jarvis-can-alerts jarvis-can-tts
journalctl -u jarvis-can-sim -u jarvis-can-alerts -u jarvis-can-tts -f
```

Las unidades usan `scripts/run-service-sim.sh`, `run-service-alerts.sh` y
`run-service-tts.sh`, que escriben los PID files en `data/` para que
`status-*.sh` y el panel (`monitor_active`) sigan funcionando. La unidad de
alertas usa `--interval 180 --initial-gap 300 --play-audio auto` y la base
`/home/arduino/JarvisCAN/data/vehicle.db`; requiere que el simulador o el
logger CAN real estén insertando muestras.

Para instalar solo el servicio de alertas (legado):

```bash
sudo ./scripts/install-alerts-service.sh
sudo systemctl status jarvis-can-alerts
```

## Verificación realizada

- El simulador generó 14 muestras de prueba en `/tmp/jarvis_test.db` con
  `--anomaly all --anomaly-every 7`: las muestras 7–11 mostraron 118 °C, 52 %
  de refrigerante, 48 % de aceite, un neumático a 162 kPa, los DTC
  `P0128,U0100` y velocidad 146 km/h; las muestras 12–13 volvieron a la
  normalidad.
- `python3 -m py_compile scripts/simulate_can.py` y
  `python3 -m py_compile scripts/can_alerts.py` pasan.
- `bash -n scripts/*.sh` pasa.
- La compilación C se hace en la placa porque el host no tiene `sqlite3.h`.
- En la placa, la base real `data/vehicle.db` se migró y siguió creciendo cada
  60 s con las columnas nuevas (más de 320 muestras al 2026-11-05 12:41 UTC).
  La muestra de 12:39:29 trajo `C0035,P0171` y `CHECK_ENGINE`.
- `can_alerts.py --only engine_temp --once --play-audio auto` generó el WAV y
  lo reprodujo en el audífono **EW02 Plus** (`played_on_device: true`,
  `audio_sink: "EW02 Plus"`). El usuario confirmó que escuchó la alerta y que
  se oye bien.
- `can_alerts.py --only dtc --once --play-audio auto` contra la base real
  reprodujo: “Se han detectado códigos de falla: C0035, P0171; avisos: testigo
  de motor”, también en el EW02 (`played_on_device: true`). El usuario
  confirmó que le llegó el mensaje de testigo de motor.
- El planificador se probó con `--interval 2 --initial-gap 1 --dry-run`: las
  seis reglas respetaron los offsets y repitieron cada 2 s; en producción se
  usan 180 s y 300 s.
- Los monitores reales quedaron activos con `./scripts/start-alerts.sh`
  (PID 7474) sobre `data/vehicle.db`. Con el desfase configurado, las seis
  reglas quedan activas alrededor de los 25 minutos desde el arranque.
- A las 12:46:54 UTC la regla programada `coolant_level` disparó por una
  anomalía de 52 %: “Se ha detectado un nivel de refrigerante riesgoso,
  medido en 52 por ciento, igual o menor al 60 por ciento”. El log registró
  `audio OK en EW02 Plus`, confirmando el ciclo automático cada 3 minutos.
- El **panel web** se desplegó con una alerta real de `oil_level` a las
  14:50:04 UTC: el WAV quedó en
  `data/alert_audio/alert_..._oil_level.wav` (371.120 bytes), la API
  `/api/alerts` devolvió `audio_url` y el panel mostró la regla, la hora y el
  mensaje. La página no usa micrófono.
- Prueba de audio del panel: el WAV archivado se sirve en
  `/alert-audio/...` y se reproduce en el navegador; si el EW02 está
  conectado, también se reproduce ahí.
- En la demo del 2026-11-11 se abrió el panel desde la PC a través de
  `http://192.168.10.1:8090/`, se tocó **Activar sonido** y una alerta nueva de
  `tire_pressure` se reprodujo completa en el navegador (WAV de 12,86 s). Los
  tres servicios systemd quedaron `enabled` y `active`.

## Limitaciones

- No hay CAN real en la UNO Q: no existe `can0`. Las presiones de neumáticos y
  los niveles se simulan con tramas ficticias `0x600`–`0x603`.
- El logger C solo funciona con una interfaz SocketCAN real. Para el auto
  hacen falta un transceptor CAN y firmware en el MCU, o un adaptador USB-CAN
  con host USB.
- Los umbrales son de demostración; un Nissan Versa 2020 real puede usar otros
  PIDs, escalas y códigos. Ajustar antes de usar en un vehículo.
- Las alertas se basan en la última muestra; si el simulador se detiene, se
  repite la última lectura. No se debe interpretar como dato en vivo.
- El desfase inicial de 25 minutos puede perder una anomalía que ocurra y
  desaparezca antes de que su regla arranque. Una vez activas, cada regla
  revisa cada 3 minutos y las anomalías duran 5 muestras (5 minutos).
- El audio se reproduce en el panel web o en el audífono; la UNO Q no
  tiene salida de audio interna utilizable.
