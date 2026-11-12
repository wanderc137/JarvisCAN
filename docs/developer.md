# JarvisCAN — Guía de desarrollador

> **Audiencia:** quien vaya a mantener, extender o portar el proyecto.
> **Alcance:** arquitectura interna, módulos, contratos de datos y procedimientos de cambio.
> **Estado:** JarvisCAN 2.0 — pipeline validado con simulación; CAN físico pendiente.

---

## 1. Mapa mental del sistema

JarvisCAN es un pipeline de cuatro etapas con interfaces de archivo:

```text
[adquisición] → SQLite → [consulta / reglas] → [voz + panel]
```

| Etapa | Proceso | Lenguaje | Entrada | Salida |
|---|---|---|---|---|
| Adquisición | `can_logger` o `simulate_can.py` | C / Python | SocketCAN, AF_UNIX o modelo interno | filas en `vehicle.db` |
| Persistencia | `db.c` | C | `VehicleSample` | tabla `vehicle_samples` |
| Consulta | `can_query` | C | argumentos CLI | tabla/JSON/CSV en stdout |
| Reglas | `can_alerts.py` | Python | últimas 20 muestras | `alerts.jsonl`, WAV, log |
| Voz | `voice-can.py` | Python | texto | `last_answer.wav/json` |
| Panel | `tts-server.py` | Python | JSONL + WAV | HTTP/JSON/HTML |
| Asistente | `jarvis-can-ask.py` | Python | pregunta NL | consulta + resumen |

La regla de oro: **los procesos no se llaman por red**. Comparten archivos y convenciones. Un servicio caído no bloquea a los demás; solo se pierde su función.

**Diagramas:** [arquitectura](assets/architecture.svg) · [despliegue](assets/deployment.svg) · [flujo de alertas](assets/alerts-flow.svg) · [rendimiento medido](assets/performance.svg).

---

## 2. Estructura del código

```text
src/
├── can_logger.c   # bucle de adquisición y CLI
├── can_query.c    # parser, SQL, formatos de salida
├── db.c / db.h    # apertura, esquema, migraciones, inserción
└── obd.c / obd.h  # SocketCAN y transporte simulado
scripts/
├── simulate_can.py    # ECU falsa con estado
├── can_alerts.py      # scheduler y 6 reglas
├── voice-can.py       # Piper/espeak, Vosk, reproducción
├── tts-server.py      # panel + API
├── jarvis-can-ask.py  # enrutamiento NL + resumen
├── build.sh           # compilación C
├── deploy-unoq.sh     # tar sobre SSH + build remoto
├── install-*.sh       # unidades systemd y sudoers
├── run-service-*.sh   # wrappers de systemd (PID + exec)
└── start/stop/status-*.sh
systemd/               # unidades declarativas
sql/schema.sql         # esquema de referencia
tests/obd_ecu_sim.c    # ECU de prueba en C
config/sudoers-jarvis-can
```

### 2.1 Convenciones

- **C11**, `-O2 -Wall -Wextra`, sin dependencias fuera de libc, libm y libsqlite3.
- Nombres de columnas y métricas en `snake_case`; textos de interfaz en español.
- Etiquetas de `can_query` sin acentos (compatibilidad de terminal); Python/HTML/JSON sí usan acentos.
- Errores a `stderr`, datos a `stdout`.
- Fechas internas en UTC (`ts_utc`, `epoch`); la interpretación local se hace al consultar.
- Los scripts Python no requieren paquetes externos salvo Vosk (opcional, en `.pylibs/`).

---

## 3. Capa de datos (`db.c` / `db.h`)

### 3.1 `VehicleSample`

Estructura plana de 25 `double` + metadatos. Los campos no leídos quedan en `NAN`; `db_insert()` los convierte a `NULL`.

```c
typedef struct {
    int64_t epoch;
    char ts_utc[32];
    char source[24];
    int pid_count;
    double speed_kph, rpm, coolant_c, engine_load_pct, throttle_pct;
    double fuel_level_pct, intake_air_c, maf_gps, fuel_pressure_kpa;
    double map_kpa, timing_advance_deg, run_time_s, battery_v, oil_temp_c;
    double barometric_kpa, short_fuel_trim_pct, long_fuel_trim_pct;
    double catalyst_temp_c, ambient_air_c, coolant_level_pct, oil_level_pct;
    double tire_fl_kpa, tire_fr_kpa, tire_rl_kpa, tire_rr_kpa;
    char dtc_codes[160];
    char warning_flags[160];
    char raw_json[2048];
} VehicleSample;
```

### 3.2 API

| Función | Contrato |
|---|---|
| `int db_open(const char *path, sqlite3 **out)` | Abre RW/CREATE con FULLMUTEX, WAL, `busy_timeout`. Devuelve 0 o error. |
| `void db_close(sqlite3 *db)` | Cierra sin fugas. |
| `int db_init(sqlite3 *db)` | Crea tabla/índice y migra columnas. Idempotente. |
| `int db_insert(sqlite3 *db, const VehicleSample *s)` | Inserta una muestra; `NAN` → `NULL`. |
| `int db_ensure_parent(const char *path)` | Crea directorios padres. |

### 3.3 Esquema

`vehicle_samples` tiene una fila por muestra:

- `id`, `ts_utc`, `epoch`, `source`, `pid_count`.
- 25 columnas `REAL`: 19 OBD-II + `coolant_level_pct`, `oil_level_pct` y las cuatro presiones.
- `dtc_codes`, `warning_flags`, `raw_json`.

Índice `idx_vehicle_samples_epoch(epoch)` para los rangos temporales. La migración consulta `PRAGMA table_info` y ejecuta `ALTER TABLE ... ADD COLUMN` solo si falta; por eso una base de una versión anterior sigue abriendo.

### 3.4 Inserción

Sentencia preparada con 32 parámetros. Se reutiliza en cada iteración del logger. `sqlite3_bind_text` usa `SQLITE_TRANSIENT` para que SQLite copie las cadenas. La transacción es implícita por inserción; con una muestra por minuto no hay presión de escritura.

---

## 4. Transporte OBD-II (`obd.c` / `obd.h`)

### 4.1 API

| Función | Contrato |
|---|---|
| `int obd_open(ObdLink *l, const char *ifname, int timeout_ms)` | Abre SocketCAN o AF_UNIX según prefijo `unix:`. |
| `void obd_close(ObdLink *l)` | Cierra el descriptor. |
| `int obd_read_pid(ObdLink *l, uint8_t pid, uint8_t *out, int maxlen)` | Devuelve bytes de payload o `-1`. |

### 4.2 Protocolo

1. Se drena el socket para descartar respuestas viejas.
2. Se envía `[0x02, 0x01, pid, 0, 0, 0, 0, 0]` a `0x7DF`.
3. Se leen tramas y se aceptan solo respuestas de `0x7E8–0x7EF`.
4. Se valida: sin `CAN_ERR_FLAG`, single-frame (`data[0] & 0xF0 == 0`), longitud suficiente, servicio `0x41` y PID coincidente.
5. Se copian `len - 2` bytes de payload.
6. Hasta 4 intentos; luego `-1` y el logger continúa con el resto.

### 4.3 Limitaciones deliberadas

- Sin ISO-TP multi-frame: los PIDs usados caben en una trama.
- Sin CAN de 29 bits: el Versa usa 11 bits para OBD-II.
- Sin DBC ni mensajes propietarios: el proyecto se limita a parámetros estándar.

### 4.4 Agregar un PID

1. Añadir la columna en `VehicleSample` (`db.h`) y en el `CREATE TABLE` de `db.c`.
2. Agregar la migración correspondiente en `db_init()`.
3. Leer el PID en `can_logger.c` y aplicar la fórmula SAE J1979.
4. Añadir la columna al `INSERT` de 32 parámetros (sube el conteo).
5. Añadir la métrica a `METRICS` en `can_query.c` y al `SELECT`.
6. Actualizar `sql/schema.sql`, el simulador (para que genere el valor) y la documentación.

---

## 5. `can_logger.c`

### 5.1 Flujo

```text
parse args → db_open → db_init → obd_open
   └→ loop:
        clock_gettime(CLOCK_REALTIME)
        construir VehicleSample (epoch, ts_utc, source)
        para cada uno de 19 PIDs: obd_read_pid + conversión + raw_json
        db_insert si pid_count > 0
        dormir hasta el siguiente instante (o saltar si ya pasó)
   └→ SIGINT/SIGTERM → db_close + obd_close
```

### 5.2 Conversiones

| PID | Señal | Fórmula |
|---|---|---|
| `0x04` | Carga | `A * 100 / 255` |
| `0x05` | Refrigerante | `A - 40` |
| `0x06/0x07` | Trims | `A / 1.28 - 100` |
| `0x0A` | Presión combustible | `A * 3` |
| `0x0B` | MAP | `A` |
| `0x0C` | RPM | `(A*256 + B) / 4` |
| `0x0D` | Velocidad | `A` |
| `0x0E` | Avance | `A / 2 - 64` |
| `0x0F` | Admisión | `A - 40` |
| `0x10` | MAF | `(A*256 + B) / 100` |
| `0x11` | Acelerador | `A * 100 / 255` |
| `0x1F` | Tiempo motor | `A*256 + B` |
| `0x2F` | Combustible | `A * 100 / 255` |
| `0x33` | Barométrico | `A` |
| `0x3C` | Catalizador | `(A*256 + B) / 10 - 40` |
| `0x42` | Batería | `(A*256 + B) / 1000` |
| `0x46` | Ambiente | `A - 40` |
| `0x5C` | Aceite | `A - 40` |

### 5.3 `--simulate`

Genera un random walk de 18 PIDs con `source="simulator"`. Es útil para probar el logger sin simulador externo, pero **no** reproduce anomalías ni frames custom. Para demos completas usar `simulate_can.py`.

---

## 6. `can_query.c`

### 6.1 Flujo

```text
parse args → validar métrica/agg/formato → resolver tiempos
→ abrir SQLite READONLY → construir SQL con sqlite3_mprintf
→ ejecutar → imprimir tabla/JSON/CSV
```

### 6.2 Lista blanca

`METRICS[]` contiene `{name, label, unit}`. La métrica se busca linealmente; si no está y no es `all`/`raw`, se aborta con código 2. `parse_agg()` acepta alias en español. El SQL solo interpola identificadores ya validados y valores numéricos; los tiempos se convierten a `epoch` antes de entrar.

### 6.3 Consultas por tipo

| Caso | SQL generado |
|---|---|
| `all` | 30 columnas, `ORDER BY epoch`, `LIMIT` |
| `raw` | `ts_utc, epoch, source, raw_json` |
| Métrica concreta | `ts_utc, epoch, <métrica>` |
| `count` | `COUNT(*)` |
| `avg`/`sum` | `COUNT(<m>), AVG/SUM(<m>)` |
| `min`/`max` | fila con `ts_utc, epoch, <m>` ordenada y `LIMIT 1` |
| `--last N` | sin `WHERE`, `LIMIT N` |

### 6.4 Salida JSON

```json
{
  "ok": true,
  "query": {
    "metric": "speed_kph", "agg": "max", "from": "-60m", "to": "now",
    "from_epoch": 0, "to_epoch": 0,
    "from_local": "...", "to_local": "...",
    "limit": 20, "order": "desc", "db": "data/vehicle.db"
  },
  "columns": ["ts_utc", "epoch", "value"],
  "rows": [{"ts_utc": "...", "epoch": 0, "value": 0.0}],
  "row_count": 1
}
```

CSV aplica comillas dobles y duplica las internas. La tabla usa ancho fijo de 22 caracteres. El conteo va a `stderr` para no contaminar `stdout`.

---

## 7. Simulador (`simulate_can.py`)

### 7.1 Modelo

`FakeEcu` mantiene estado y avanza con `dt`. Cada señal usa un objetivo y un suavizado exponencial (`τ` distinto por señal). El ciclo de 300 s define el objetivo de velocidad, acelerador y carga; el resto se deriva.

### 7.2 Frames custom

| ID | Contenido | Codificación |
|---|---|---|
| `0x600` | Presión de las 4 ruedas | kPa / 2 en un byte cada una |
| `0x601` | Niveles de refrigerante y aceite | porcentaje en un byte cada uno |
| `0x602` | Hasta 2 DTC | longitud + ASCII |
| `0x603` | Máscara de avisos | bits `CHECK_ENGINE`…`HIGH_COOLANT_TEMP` |

### 7.3 Anomalías

`--anomaly random|none|all|engine_temp|coolant_level|tire_pressure|oil_level|dtc|overspeed`. Cada anomalía se mantiene 5 muestras y luego vuelve a la normalidad. `--anomaly-every N` controla la frecuencia; `--dtc-every N` fuerza códigos, pospuestos si hay anomalía activa.

### 7.4 Reanudación

Al arrancar lee la última fila. Si existe, continúa el ciclo y avanza `min(now - last, 300)` segundos para no generar un salto enorme tras una pausa. `--reset` reinicia el estado; `--no-resume` ignora la base.

---

## 8. Motor de alertas (`can_alerts.py`)

### 8.1 Scheduler

Cada regla tiene `next_due` monotónico. Al arrancar se asigna `now + i * initial_gap` (5 min). El bucle duerme en trozos de ≤5 s para responder a señales. Cuando vence una regla, se evalúa, se guarda estado y se reprograma `now + interval` (3 min).

### 8.2 Evaluación

`fetch_samples(limit)` consulta las últimas N muestras e introspecciona las columnas disponibles para tolerar bases viejas. Cada regla devuelve un mensaje o `None`.

| Regla | Lógica |
|---|---|
| `engine_temp` | valor actual y media móvil; dispara por absoluto o por desviación |
| `coolant_level` | umbral directo |
| `tire_pressure` | compara cada rueda contra umbral y contra 75 % de la media |
| `oil_level` | umbral directo |
| `dtc` | unión de códigos/avisos en ventana; diferencia contra `dtc_seen`/`warning_seen` |
| `overspeed` | flanco de subida con flag `overspeed_active` |

### 8.3 Audio y registro

`speak()` ejecuta `voice-can.sh --tts-test <mensaje> --play-audio <modo>` con timeout. Luego lee `data/last_answer.json` para saber si se reprodujo y en qué sink; copia el WAV a `data/alert_audio/alert_<time_ns>_<rule>.wav`; poda a `--alert-audio-keep`.

`log_event()` escribe una línea JSON con `ts`, `epoch`, `rule`, `message`, `audio_generated`, `audio_ok`, `played_on_device`, `audio_sink`, `audio_file`, y una línea humana en `alerts.log`.

### 8.4 Agregar una regla

1. Añadir el nombre a `RULE_ORDER`.
2. Implementar `check_<regla>(samples, args, state)`.
3. Añadir el umbral al parser de argumentos y a los valores por defecto.
4. Añadir la etiqueta en `RULE_LABELS` del panel y el color si corresponde.
5. Añadir la tarjeta en el HTML del panel (opcional).
6. Documentar en `docs/ALERTS.md` y probar con `--only`.

---

## 9. Voz (`voice-can.py`)

### 9.1 Perfiles

| Perfil | `length_scale` | `noise_w` | Silencio entre frases |
|---|---|---|---|
| `flat` | 1.0 | 0.8 | 0.0 s |
| `human` | 1.0 | 0.8 | 0.35 s (segmentación) |
| `human-lite` | 1.02 | 0.90 | 0.45 s |

Variables: `JARVIS_TTS_PROFILE`, `JARVIS_TTS_ENGINE`, `JARVIS_TTS_LENGTH_SCALE`, `JARVIS_TTS_NOISE_SCALE`, `JARVIS_TTS_NOISE_W`, `JARVIS_TTS_SENTENCE_SILENCE`.

### 9.2 Síntesis y reproducción

- **Piper:** invoca el binario ARM64 con el modelo ONNX y `espeak-ng-data`; para `human`, sintetiza por frases y concatena WAVs con silencio.
- **espeak-ng:** fallback si Piper falta o falla.
- **Reproducción:** enumera fuentes/sinks con `pw-dump` en la sesión de `lightdm` (vía `sudo -n -u lightdm`), elige el sink y ejecuta `pw-cat --target`.
- **Entrada:** Vosk transcribe un WAV de IP Webcam, remuestreado de 44,1 a 16 kHz.
- **Salidas:** `data/last_answer.wav` (mono 22,05 kHz PCM) y `.json` con metadatos.

### 9.3 Añadir una voz

1. Descargar el `.onnx` y su `.onnx.json` en `models/piper/`.
2. Verificar que `vendor/piper/espeak-ng-data` exista.
3. Probar `voice-can.sh --tts-test "..." --tts-model models/piper/<voz>.onnx --play-audio off`.
4. Medir latencia y calidad; registrar el resultado en `docs/VOICE-HUMAN-LITE.md`.
5. Cambiar el default solo si mejora la relación latencia/calidad.

---

## 10. Panel (`tts-server.py`)

### 10.1 Componentes

- `ThreadingHTTPServer` en `0.0.0.0:8090` (configurable con `--host`, `--port`).
- HTML embebido con CSS y JS inline; sin build ni CDN.
- `load_alerts()` lee el JSONL en orden inverso, resuelve `audio_url` solo si el archivo existe y ordena por `epoch`/`ts`.
- `monitor_active()` lee `data/can_alerts.pid` y comprueba el PID con `os.kill(pid, 0)`.
- `do_POST` responde 404: no hay endpoints de escritura.

### 10.2 Añadir un endpoint

1. Implementar `do_GET_<nombre>()`.
2. Validar y acotar parámetros (límites, rutas).
3. Responder JSON con `Content-Type: application/json`.
4. Añadir `Cache-Control: no-store` si el dato cambia.
5. Documentar en `docs/datasheet.md` y en el README.
6. Probar con `curl` y con el panel.

---

## 11. Asistente NL (`jarvis-can-ask.py`)

### 11.1 Pipeline

```text
pregunta → Ollama /api/chat (JSON) → normalize_route
        → apply_question_hints → fallback_route si hace falta
        → can_query --format json → summarize determinista
```

### 11.2 Por qué el resumen es determinista

Un modelo de 0.5B alucina cifras con facilidad. Se decidió que el LLM solo enrute; los números provienen de SQLite y las frases de plantillas. Así una respuesta puede ser lenta, pero no inventa un valor.

### 11.3 Extender el vocabulario

- Añadir sinónimos en `apply_question_hints()` (agregaciones, rangos, límites).
- Añadir `STRONG_HINTS` para métricas que el modelo confunde (niveles, ruedas).
- Añadir el par clave→métrica en `fallback_route()`.
- Probar con `--show-query` y verificar que el `can_query` generado es el esperado.

---

## 12. Servicios y despliegue

### 12.1 Unidades

| Unidad | Ejecuta | Reinicio | Limpieza |
|---|---|---|---|
| `jarvis-can-sim` | `run-service-sim.sh` | 10 s | PID, sockets |
| `jarvis-can-alerts` | `run-service-alerts.sh` | 10 s | PID |
| `jarvis-can-tts` | `run-service-tts.sh` | 5 s | PID |
| `jarvis-can-logger` | `bin/can_logger --iface can0` | 10 s | — |

Todas usan `User=arduino`, `WorkingDirectory=/home/arduino/JarvisCAN` y `PYTHONUNBUFFERED=1`. Los wrappers escriben `$$` en `data/*.pid` y hacen `exec` para que systemd controle el proceso real.

### 12.2 Instalación

- `install-all-services.sh`: requiere root; copia sim/alerts/tts, `daemon-reload`, `enable --now`.
- `install-service.sh`: copia el logger y el sudoers acotado; valida con `visudo -cf`.

### 12.3 Despliegue

`deploy-unoq.sh` empaqueta con `tar` sobre SSH, excluye artefactos y datos, reconstruye en destino y crea atajos. Es idempotente y no toca la base remota.

---

## 13. Pruebas y verificación

### 13.1 Pruebas manuales mínimas

```bash
# Compilación limpia
./scripts/build.sh

# Simulador: 5 muestras con anomalías
./scripts/simulate_can.py --count 5 --anomaly all --reset

# Consulta y formatos
./bin/can_query --last 5
./bin/can_query --metric rpm --agg avg --format json
./bin/can_query --metric coolant_c --format csv

# Reglas sin audio
./scripts/can_alerts.py --dry-run --once --only tire_pressure

# Voz aislada
./scripts/voice-can.sh --tts-test "Prueba" --play-audio off

# Panel
curl -s http://127.0.0.1:8090/healthz
curl -s "http://127.0.0.1:8090/api/alerts?limit=1"

# Asistente
./scripts/ask-can.sh --show-query "¿Cuál es la velocidad máxima de hoy?"
```

### 13.2 Prueba con hardware CAN (cuando exista)

1. `lsusb` y `ip -details link show can0` para confirmar el adaptador.
2. `candump can0` con el auto encendido; verificar tráfico.
3. `./bin/can_logger --iface can0 --once --verbose`.
4. Comparar valores con un escáner OBD-II de referencia.
5. Recién entonces cambiar la unidad del logger a `can0` y deshabilitar el simulador.

### 13.3 Criterios de aceptación

- `can_logger` inserta una fila por intervalo sin perder el ritmo.
- `can_query` devuelve los tres formatos y respeta límites y rangos.
- Una anomalía de prueba dispara su regla y genera un WAV reproducible.
- El panel muestra la alerta y `monitor_active: true`.
- El asistente responde con una cifra que coincide con `can_query`.

---

## 14. Deuda técnica conocida

| Tema | Estado | Camino sugerido |
|---|---|---|
| CAN físico | Bloqueado por hardware | USB-CAN + prueba en bus; o transceptor + firmware Zephyr |
| ISO-TP multi-frame | No implementado | Añadir capa ISO-TP si se necesitan PIDs largos o DTC detallados |
| Auth/TLS del panel | Ausente | Reverse proxy con TLS y basic auth, o token |
| NTP | Ausente | Servicio `systemd-timesyncd` con RTC o GPS |
| Modelo NL | 0.5B, limitado | Evaluar 1.5B si la RAM lo permite; mantener resumen determinista |
| Audio interno | Inservible | USB audio o Bluetooth A2DP; documentar el sink |
| Pruebas automatizadas | Manuales | Añadir `pytest` para reglas y un test de integración del pipeline |
| `requirements.txt` | Inexistente | Crear solo si se agregan dependencias Python; hoy la stdlib alcanza |

---

## 15. Referencias

- [`../README.md`](../README.md) — visión general.
- [`datasheet.md`](datasheet.md) — manual de usuario.
- [`INSTALL.md`](INSTALL.md) — instalación.
- [`HARDWARE.md`](HARDWARE.md) — hardware y CAN.
- [`ALERTS.md`](ALERTS.md) — reglas y umbrales.
- [`QUERIES.md`](QUERIES.md) — consultas.
- [`VOICE.md`](VOICE.md) y [`VOICE-HUMAN-LITE.md`](VOICE-HUMAN-LITE.md) — voz.
- [`BITACORA.md`](BITACORA.md) — decisiones y lecciones.
- [`REFERENCES.md`](REFERENCES.md) — enlaces externos.
