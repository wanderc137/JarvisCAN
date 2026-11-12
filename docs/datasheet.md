# JarvisCAN — Datasheet y manual de usuario

> **Documento:** especificaciones y guía de operación
> **Proyecto:** JarvisCAN 2.0
> **Plataforma:** Arduino UNO Q (Qualcomm QRB2210, Debian 13, STM32U585)
> **Vehículo objetivo:** Nissan Versa 2020 (OBD-II sobre CAN)
> **Estado:** pipeline completo validado con simulación; CAN físico pendiente
> **Licencia:** MIT © 2026 wanderc137

---

## 1. Resumen ejecutivo

JarvisCAN adquiere parámetros del vehículo por OBD-II, los almacena en SQLite y los pone a disposición de tres consumidores: una herramienta de consulta en C, un motor de alertas con voz sintetizada y un panel web. Todo corre en la placa, sin nube y sin backend.

El sistema está diseñado para funcionar igual con datos reales o simulados. Hoy la UNO Q no expone `can0`, por lo que la adquisición real no está disponible; el simulador reproduce el contrato de datos y permite validar el resto del pipeline de extremo a extremo.

| Indicador | Valor |
|---|---|
| Métricas almacenadas | 25 columnas numéricas + DTC, avisos y JSON crudo |
| PIDs OBD-II leídos por el logger | 19 |
| Reglas de alerta | 6 |
| Formatos de consulta | tabla, JSON, CSV |
| Servicios systemd | 3 activos (sim, alerts, tts) + 1 preparado (logger) |
| Puerto del panel | 8090/TCP |
| Modelo de lenguaje | `qwen2.5:0.5b-instruct-q4_K_M` local |
| Voz | Piper `es_MX-claude-high`, perfil human-lite; fallback espeak-ng |

---

## 2. Alcance y estado

### 2.1 Lo que el producto hace hoy

- Simula una ECU OBD-II con ciclo de conducción de 300 s y seis tipos de anomalía.
- Inserta una muestra por minuto en `data/vehicle.db` (configurable).
- Permite consultar 25 métricas por rango de tiempo, agregación y formato.
- Evalúa seis reglas cada tres minutos y genera mensajes hablados en español.
- Publica un panel web con el estado de las reglas, el feed y los audios.
- Responde preguntas en lenguaje natural con un LLM local y resumen determinista.

### 2.2 Lo que el producto no hace

- No se conecta al bus CAN del vehículo: falta adaptador USB-CAN o transceptor.
- No borra DTC, no codifica componentes ni escribe en la ECU.
- No interpreta mensajes propietarios del Versa ni ISO-TP multi-frame.
- No autentica usuarios ni cifra el panel.
- No sincroniza el reloj por NTP.

### 2.3 Estados posibles de una muestra

| `source` | Origen | Significado |
|---|---|---|
| `can_sim` | `simulate_can.py` | Muestra del simulador con frames custom |
| `simulator` | `can_logger --simulate` | Random walk interno del logger |
| `can0` | SocketCAN real | Reservado para hardware físico |

---

## 3. Especificaciones técnicas

### 3.1 Plataforma

| Parámetro | Valor |
|---|---|
| MPU | Qualcomm QRB2210, aarch64, 4 núcleos |
| RAM | 3,6 GiB (compartida con el SO) |
| SO | Debian 13 “trixie” |
| MCU | STM32U585 con Zephyr |
| Almacenamiento | Almacenamiento interno de la placa |
| Red | WiFi; perfil de demo `DEMO-UNOQ` |
| Audio | Tarjeta `ArduinoImolaHPH` no funcional; salida por Bluetooth A2DP o navegador |
| CAN del MCU | FDCAN1: D4 = TX (PA12), D5 = RX (PA11), lógica 3,3 V |

### 3.2 Software

| Componente | Versión / requisito |
|---|---|
| Compilador | GCC con C11 (`-O2 -Wall -Wextra -std=c11`) |
| SQLite | 3.x con `libsqlite3-dev` |
| Python | 3.11 o superior (probado en Debian 13) |
| systemd | El de Debian 13 (probado en la placa) |
| Piper | binario ARM64 2023.11.14-2 + `espeak-ng-data` |
| Vosk | 0.3.45 (opcional) |
| Ollama | local en `127.0.0.1:11434` |
| Modelo LLM | `qwen2.5:0.5b-instruct-q4_K_M` |

### 3.3 Base de datos

Archivo único `data/vehicle.db`, modo WAL.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | Autoincremental |
| `ts_utc` | TEXT | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) |
| `epoch` | INTEGER | Segundos Unix; indexado |
| `source` | TEXT | Origen de la muestra |
| `pid_count` | INTEGER | PIDs válidos en la muestra |
| 25 columnas | REAL | Métricas (ver tabla 4.1) |
| `dtc_codes` | TEXT | Códigos separados por coma |
| `warning_flags` | TEXT | Avisos separados por coma |
| `raw_json` | TEXT | JSON crudo con valores y frames |

PRAGMAs: `journal_mode=WAL`, `synchronous=NORMAL`, `temp_store=MEMORY`, `busy_timeout=5000`.

### 3.4 Dimensionamiento medido

| Métrica | Valor |
|---|---|
| Muestras inspeccionadas | 436 |
| Tamaño del archivo | 401.408 bytes |
| Páginas | 98 × 4096 bytes |
| Densidad | ≈ 920 bytes por fila |
| Ritmo | 1 muestra/min ⇒ ~1,3 MB/día ⇒ ~40 MB/mes |

Los audios de alerta se podan a 200 archivos; cada WAV ronda cientos de KB.

---

## 4. Manual de usuario

### 4.1 Métricas disponibles

| Nombre | Etiqueta | Unidad |
|---|---|---|
| `speed_kph` | Velocidad | km/h |
| `rpm` | RPM | rpm |
| `coolant_c` | Temperatura de refrigerante | °C |
| `engine_load_pct` | Carga del motor | % |
| `throttle_pct` | Acelerador | % |
| `fuel_level_pct` | Nivel de combustible | % |
| `intake_air_c` | Temperatura de admisión | °C |
| `maf_gps` | MAF | g/s |
| `fuel_pressure_kpa` | Presión de combustible | kPa |
| `map_kpa` | MAP | kPa |
| `timing_advance_deg` | Avance de encendido | ° |
| `run_time_s` | Tiempo de motor | s |
| `battery_v` | Voltaje de batería | V |
| `oil_temp_c` | Temperatura de aceite | °C |
| `barometric_kpa` | Presión barométrica | kPa |
| `short_fuel_trim_pct` | STFT | % |
| `long_fuel_trim_pct` | LTFT | % |
| `catalyst_temp_c` | Temperatura de catalizador | °C |
| `ambient_air_c` | Temperatura ambiente | °C |
| `coolant_level_pct` | Nivel de refrigerante | % |
| `oil_level_pct` | Nivel de aceite | % |
| `tire_fl_kpa` | Presión neumático delantero izquierdo | kPa |
| `tire_fr_kpa` | Presión neumático delantero derecho | kPa |
| `tire_rl_kpa` | Presión neumático trasero izquierdo | kPa |
| `tire_rr_kpa` | Presión neumático trasero derecho | kPa |

### 4.2 Consultas

```bash
# Últimas 10 muestras en tabla
./bin/can_query --last 10

# Máximo de velocidad de la última hora en JSON
./bin/can_query --metric speed_kph --agg max --from -60m --format json

# Promedio de RPM de hoy
./bin/can_query --metric rpm --agg avg --from today

# Refrigerante de las últimas 24 horas en CSV
./bin/can_query --metric coolant_c --from -24h --format csv

# Cantidad de muestras de la última semana
./bin/can_query --metric all --agg count --from -7d

# Catálogo completo
./bin/can_query --list-metrics
```

Rangos aceptados: `now`, `today`/`hoy`, `-30s`, `-15m`, `-24h`, `-7d`, `-2w`, ISO-8601 con o sin `Z`. Sin `--to`, el límite es “ahora”.

Salidas: `0` correcto, `2` parámetro inválido, `3` error de base o SQL. En formatos no JSON, `filas: N` se imprime en `stderr`.

### 4.3 Panel web

Abrir `http://<IP-de-la-placa>:8090/`.

| Zona | Qué muestra |
|---|---|
| Radar superior | Actividad del monitor y estado general |
| Seis tarjetas | Regla, umbral, contador y estado “En guardia”/“Disparó” |
| Feed | Últimas alertas con hora, regla, mensaje y audio |
| Ecualizador | Indicador animado de actividad |
| `monitor_active` | Si el proceso de alertas está vivo |

El panel sondea `/api/alerts` cada 2 segundos. No requiere autenticación y está pensado para LAN.

### 4.4 API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | HTML del panel |
| GET | `/healthz` | `{"ok":true,"monitor_active":bool}` |
| GET | `/api/alerts?limit=60` | Alertas (1–200) |
| GET | `/alert-audio/<archivo>` | WAV de una alerta |
| GET | `/answer.json` | Última respuesta del asistente |
| GET | `/answer.wav` | Último audio generado |
| GET | `/silence.wav` | Silencio de 0,12 s a 16 kHz |
| POST | cualquiera | 404 |

Ejemplo:

```bash
curl -s http://192.168.10.75:8090/api/alerts?limit=5 | python3 -m json.tool
```

Respuesta:

```json
{
  "alerts": [
    {
      "id": "1762347004123456789-oil_level",
      "ts": "2026-11-05 14:50:04",
      "epoch": 1762354204,
      "rule": "oil_level",
      "rule_label": "Nivel de aceite",
      "message": "Se ha detectado un nivel de aceite riesgoso...",
      "audio_url": "/alert-audio/alert_1762354204123456789_oil_level.wav",
      "played_on_device": true,
      "audio_sink": "bluez_output..."
    }
  ],
  "count": 1,
  "monitor_active": true
}
```

### 4.5 Alertas

| Regla | Condición | Umbral configurable |
|---|---|---|
| `engine_temp` | actual ≥ 105 °C o +15 °C sobre la media | `--temp-abs`, `--temp-deviation` |
| `coolant_level` | ≤ 60 % | `--coolant-level` |
| `tire_pressure` | ≤ 180 kPa o 25 % bajo la media | `--tire-kpa`, `--tire-drop-pct` |
| `oil_level` | ≤ 60 % | `--oil-level` |
| `dtc` | códigos o avisos nuevos en 20 muestras | `--dtc-window` |
| `overspeed` | > 130 km/h en flanco de subida | `--speed-limit` |

Planificación: desfase inicial de 5 minutos entre reglas (0, 5, 10, 15, 20, 25) y luego una revisión cada 3 minutos por regla. El estado se guarda en `data/alerts_state.json`.

### 4.6 Voz

```bash
# Probar la síntesis sin reproducir
./scripts/voice-can.sh --tts-test "Sistema listo" --play-audio off

# Comparar perfiles
./scripts/tts-compare.sh --tts-profile flat
./scripts/tts-compare.sh --tts-profile human-lite
```

Perfil por defecto: `human-lite`, voz `es_MX-claude-high`, 0.45 s entre frases. Si Piper falla, se usa espeak-ng. La reproducción usa `pw-cat` sobre PipeWire; si no hay sink, el WAV queda disponible en `data/last_answer.wav` y en el panel.

### 4.7 Asistente en lenguaje natural

```bash
./scripts/ask-can.sh "¿Cuál fue la velocidad máxima en la última hora?"
./scripts/ask-can.sh --show-query "¿Cuántas muestras hay hoy?"
./scripts/ask-can.sh            # interactivo, prompt vos>
```

El LLM solo elige métrica, agregación y rango. La cifra y la redacción provienen de `can_query` y de plantillas deterministas. Sin Ollama, se usa la ruta heurística por palabras clave.

---

## 5. Instalación y puesta en marcha

### 5.1 Dependencias del sistema

```bash
sudo apt update
sudo apt install -y build-essential libsqlite3-dev sqlite3 can-utils espeak-ng
```

No hay `requirements.txt`: los módulos Python usan la biblioteca estándar (`http.server`, `sqlite3`, `json`, `subprocess`, `argparse`). Las dependencias opcionales (Vosk) se instalan en `.pylibs/` y se activan con `PYTHONPATH` desde los wrappers.

### 5.2 Compilación

```bash
./scripts/build.sh
```

Produce:

- `bin/can_logger` — `src/can_logger.c`, `src/obd.c`, `src/db.c`, `-lsqlite3 -lm`.
- `bin/can_query` — `src/can_query.c`, `-lsqlite3 -lm`.
- `bin/obd_ecu_sim` — `tests/obd_ecu_sim.c`.

### 5.3 Servicios

```bash
sudo ./scripts/install-all-services.sh   # sim, alerts, tts
sudo ./scripts/install-service.sh        # logger + sudoers acotado
systemctl status jarvis-can-sim jarvis-can-alerts jarvis-can-tts
```

### 5.4 Verificación

```bash
./bin/can_query --last 3
curl -s http://127.0.0.1:8090/healthz
curl -s "http://127.0.0.1:8090/api/alerts?limit=1"
./scripts/can_alerts.py --list-rules
```

---

## 6. Operación y mantenimiento

### 6.1 Ciclo diario

| Tarea | Comando |
|---|---|
| Arrancar todo | `./scripts/start-all.sh` |
| Estado | `./scripts/status-all.sh` |
| Detener | `./scripts/stop-all.sh` |
| Logs de alertas | `journalctl -u jarvis-can-alerts -f` |
| Logs del panel | `journalctl -u jarvis-can-tts -f` |

### 6.2 Copia de seguridad

```bash
sqlite3 data/vehicle.db ".backup 'respaldo-$(date +%F).db'"
```

No copiar `-wal` y `-shm` por separado con el servicio activo; usar `.backup` o detener el escritor.

### 6.3 Poda

- Audios de alerta: automática, últimos 200 (`--alert-audio-keep`).
- Base: manual. Con ~40 MB/mes, una rotación trimestral es razonable.
- Logs: `journalctl --vacuum-time=30d` si el almacenamiento se agota.

### 6.4 Calibración

Los umbrales por defecto son de demostración, no valores de fábrica del Versa. Antes de usar datos reales:

1. Registrar una sesión normal y calcular media y desviación de temperatura, niveles y presiones.
2. Ajustar `--temp-abs`, `--temp-deviation`, `--coolant-level`, `--oil-level`, `--tire-kpa` y `--tire-drop-pct`.
3. Probar con `--dry-run --once` antes de habilitar audio.
4. Confirmar los mensajes con `--tts-test`.
5. Documentar los valores elegidos en la bitácora.

---

## 7. Solución de problemas

| Síntoma | Diagnóstico | Solución |
|---|---|---|
| Panel no responde | `systemctl status jarvis-can-tts` | Reiniciar el servicio; revisar `TTS_PORT` |
| Sin alertas | `./bin/can_query --last 3` | Verificar que el simulador escriba; revisar journal |
| `monitor_active: false` | PID ausente o proceso muerto | `systemctl restart jarvis-can-alerts` |
| Sin audio | `voice-can.sh --tts-test` | Instalar Piper o usar `--tts-engine espeak` |
| Audio sin salida | `--list-sources` | Elegir sink; usar el navegador como salida |
| `can0` no existe | `ip link show can0` | Usar simulador o `--iface unix:` |
| Base bloqueada | `fuser data/vehicle.db` | Esperar; revisar `busy_timeout`; no borrar WAL en caliente |
| Timestamps raros | `date -u` | Sin NTP; ajustar reloj manualmente |
| LLM no disponible | `ollama list` | Iniciar Ollama o usar la heurística |
| DNAT inaccesible | Probar IP directa | Revisar hairpin SNAT en el router |
| Alertas repetidas | Estado persistente | `./scripts/can_alerts.py --reset-state` |
| Audio antiguo | Poda | Ajustar `--alert-audio-keep` |

---

## 8. Seguridad

- **Sin nube:** no hay telemetría ni cuentas; todo queda en la placa.
- **Solo lectura:** consultas y alertas abren SQLite en modo lectura.
- **SQL parametrizado por lista blanca:** no se concatena entrada del usuario.
- **Path traversal:** el servidor de audio confina las rutas a `data/alert_audio/`.
- **Sudoers mínimo:** solo `systemctl start|stop|restart jarvis-can-logger`.
- **Riesgos:** panel sin auth/TLS, DNAT de demo, SSH por clave, sistema sin actualizaciones automáticas.
- **Recomendación para producción:** TLS, autenticación, VLAN separada, firewall por puerto y respaldo cifrado.

---

## 9. Glosario

| Término | Definición |
|---|---|
| **CAN** | Bus serie diferencial usado en automoción. |
| **OBD-II** | Norma de diagnóstico a bordo; en este proyecto, PIDs sobre CAN. |
| **PID** | Identificador de parámetro OBD-II (p. ej. `0x0D` velocidad). |
| **DTC** | Código de diagnóstico de falla (p. ej. `P0300`). |
| **SocketCAN** | Implementación CAN del kernel Linux; interfaz `can0`. |
| **WAL** | Write-Ahead Logging de SQLite; lectores concurrentes. |
| **DNAT** | Traducción de destino; publica un puerto interno en otra IP. |
| **Hairpin SNAT** | SNAT para que clientes de la misma LAN entren por la IP pública del router. |
| **TTS** | Text-to-Speech; aquí Piper o espeak-ng. |
| **LLM** | Modelo de lenguaje; aquí Qwen2.5 0.5B vía Ollama. |

---

## 10. Referencias internas

- [`../README.md`](../README.md) — visión general y arquitectura.
- [`INSTALL.md`](INSTALL.md) — instalación detallada.
- [`HARDWARE.md`](HARDWARE.md) — hardware y opciones de CAN.
- [`ALERTS.md`](ALERTS.md) — reglas y evidencias.
- [`QUERIES.md`](QUERIES.md) — consultas y métricas.
- [`VOICE.md`](VOICE.md) — voz y audio.
- [`VOICE-HUMAN-LITE.md`](VOICE-HUMAN-LITE.md) — perfil human-lite.
- [`BITACORA.md`](BITACORA.md) — historia y decisiones.
- [`developer.md`](developer.md) — guía de desarrollador.
- [`REFERENCES.md`](REFERENCES.md) — enlaces externos.
