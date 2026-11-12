# Instalación y despliegue

Esta guía reproduce el entorno verificado en la Arduino UNO Q (MPU Linux
Qualcomm QRB2210, Debian 13 trixie, aarch64) y en un equipo de desarrollo
Linux.

## 1. Requisitos

### Placa

- Arduino UNO Q con Debian 13 (trixie), 4 núcleos y 3,6 GiB de RAM.
- Acceso SSH por clave:
  `ssh -p 22 -i ~/.ssh/unoq_key arduino@192.168.10.75`.
- Red WiFi con IP fija (en el equipo de referencia, `192.168.10.75`, perfil `DEMO-UNOQ`).
- Espacio libre en `/home/arduino` (modelos, base y dependencias).

### Equipo de desarrollo

- Bash, `gcc`, `make`, `sqlite3`, `ssh`, `scp`, `tar`, `curl`.
- Opcional: `gh` autenticado para publicar el repositorio.

## 2. Paquetes del sistema en la placa

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  sqlite3 build-essential libsqlite3-dev can-utils espeak-ng
```

- `sqlite3`: inspección manual de la base.
- `build-essential` + `libsqlite3-dev`: compilación de los binarios C.
- `can-utils`: `candump`, `cansend`, `ip link` para CAN real.
- `espeak-ng`: respaldo de síntesis de voz (Piper es el motor principal).

No se instala nada en el host de desarrollo para el funcionamiento normal:
la compilación y la ejecución se hacen en la placa.

## 3. Copiar el proyecto y compilar

Desde el directorio del proyecto:

```bash
./scripts/build.sh
```

Genera:

```text
bin/can_logger      logger OBD-II por SocketCAN
bin/can_query       consultas parametrizadas a SQLite
bin/obd_ecu_sim     ECU OBD-II de prueba por socket Unix
```

Para desplegar en la placa:

```bash
./scripts/deploy-unoq.sh
```

Variables opcionales:

```bash
UNOQ_HOST=192.168.10.75 \
UNOQ_USER=arduino \
UNOQ_KEY=$HOME/.ssh/unoq_key \
UNOQ_DIR=/home/arduino/JarvisCAN \
./scripts/deploy-unoq.sh
```

El script copia el árbol (sin `.git`, `bin`, bases ni `__pycache__`) y compila
en la placa. No copia modelos ni `.pylibs`; esos se instalan una vez.

## 4. Ollama y modelo local

El proyecto usa Ollama como modelo de lenguaje local. En la placa de
referencia ya está instalado en `/home/arduino/ollama` y corre como servicio
`ollama.service`.

Verificación:

```bash
systemctl is-active ollama
curl -s http://127.0.0.1:11434/api/tags | head
```

Modelo recomendado para esta placa (3,6 GiB):

```bash
ollama pull qwen2.5:0.5b-instruct-q4_K_M
```

El modelo `qwen2.5:1.5b-instruct-q4_K_M` también está disponible para más
calidad, a costa de latencia. El asistente usa el 0.5B por defecto.

Configuración del servicio de referencia:

```ini
OLLAMA_MODELS=/home/arduino/.ollama/models
OLLAMA_HOST=127.0.0.1:11434
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1
OLLAMA_KEEP_ALIVE=5m
OLLAMA_CONTEXT_LENGTH=4096
OLLAMA_NUM_THREADS=4
```

El puerto 11434 queda en loopback: no se expone a la red.

## 5. Vosk para reconocimiento de voz

Vosk corre localmente; no se envía audio a ningún servicio.

### 5.1 Modelo

Descargar y descomprimir el modelo español pequeño:

```bash
mkdir -p models
curl -L -o /tmp/vosk-model-small-es-0.42.zip \
  https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip
unzip -q /tmp/vosk-model-small-es-0.42.zip -d models/
```

Debe quedar:

```text
models/vosk-model-small-es-0.42/
```

El modelo pesa unos 58 MB y está excluido de Git.

### 5.2 Dependencias Python

El proyecto carga las dependencias desde `.pylibs` (sin instalar en el
Python del sistema):

```bash
mkdir -p .pylibs
python3 -m pip install --target .pylibs vosk==0.3.45
```

Si el `pip` del sistema no está disponible, se puede usar un `venv` o copiar
las ruedas aarch64 desde otro equipo. `vosk` importa `srt`; si falta, copiar
`srt.py` del sdist `srt==3.5.3` a `.pylibs/srt.py`.

Verificación:

```bash
PYTHONPATH=$PWD/.pylibs python3 - <<'PY'
import vosk
m = vosk.Model("models/vosk-model-small-es-0.42")
print("Vosk OK")
PY
```

### 5.3 Micrófono

La vía verificada es la app **IP Webcam** del teléfono:

```text
http://192.168.1.198:8080/audio.wav
```

Formato: WAV 44.100 Hz, mono, 16 bits. El script remuestrea a 16 kHz y
normaliza la ganancia antes de pasarlo a Vosk.

El micrófono interno de la placa y el de los AirPods no funcionaron; ver
[VOICE.md](VOICE.md).

### 5.4 TTS: Piper

Piper es el motor de voz por defecto. Se instala dentro del proyecto, sin
paquetes del sistema:

```bash
./scripts/install-piper.sh
```

Descarga el binario ARM64 en `vendor/piper/` y la voz
`es_MX-claude-high` en `models/piper/` (unos 90 MB en total). El perfil
`human-lite` es el predeterminado; se puede cambiar con `--tts-profile` o
`JARVIS_TTS_PROFILE`. No se
versionan.

Voces alternativas:

```bash
./scripts/install-piper.sh --voice es_ES-davefx-medium
./scripts/install-piper.sh --voice es_AR-daniela-high
```

Verificación:

```bash
./scripts/voice-can.sh --tts-test "Hola, soy Jarvis."
```

Debe imprimir la ruta de `data/last_answer.wav` y dejar un WAV mono a
22.050 Hz. Si Piper no está instalado o falla, `voice-can.py` usa
`espeak-ng` automáticamente.

### 5.5 Simulación con anomalías y alertas por voz

El simulador puede inyectar valores fuera de rango, DTC y warnings para
probar las reglas:

```bash
# Anomalías aleatorias cada 7 muestras, ventana de 5 muestras
python3 scripts/simulate_can.py --db data/vehicle.db --interval 60 --count 0

# Forzar todas las anomalías en una base de prueba
python3 scripts/simulate_can.py --db /tmp/jarvis_test.db \
  --anomaly all --anomaly-every 7 --count 14
```

Los monitores evalúan seis reglas con un desfase inicial de 5 minutos y luego
cada 3 minutos: temperatura del motor, nivel de refrigerante, presión de
neumáticos, nivel de aceite, DTC/warnings y exceso de velocidad. El arranque
de la demo intenta forzar un DTC cada 10 muestras (`CAN_SIM_DTC_EVERY=10`);
si coincide con otra anomalía se pospone. La regla DTC busca en las últimas
20 muestras (`--dtc-window`).

```bash
# Prueba sin audio
python3 scripts/can_alerts.py --once --dry-run

# Una regla con audio real
python3 scripts/can_alerts.py --only engine_temp --once --play-audio on

# Monitores en segundo plano
./scripts/start-alerts.sh
./scripts/status-alerts.sh
./scripts/stop-alerts.sh
```

Los detalles de umbrales, offsets y servicio systemd están en
[ALERTS.md](ALERTS.md).

## 6. Servicios systemd y arranque

### Autoarranque de la demo

La demo corre con tres unidades systemd habilitadas, que arrancan solas con la
placa y se reinician si fallan:

| Unidad | Proceso | Puerto |
|---|---|---|
| `jarvis-can-sim` | Simulador OBD-II | — |
| `jarvis-can-alerts` | Monitores de 6 reglas + TTS | — |
| `jarvis-can-tts` | Panel web de alertas | `0.0.0.0:8090` |

Instalación o reinstalación (como root, una vez):

```bash
sudo ./scripts/install-all-services.sh
systemctl is-enabled jarvis-can-sim jarvis-can-alerts jarvis-can-tts
systemctl is-active jarvis-can-sim jarvis-can-alerts jarvis-can-tts
journalctl -u jarvis-can-sim -u jarvis-can-alerts -u jarvis-can-tts -f
```

Las unidades usan los wrappers `scripts/run-service-*.sh`, que escriben los
PID files en `data/` para que `status-*.sh` y el panel sigan funcionando.
Las tres tienen `Restart=always`.

### Arranque manual (desarrollo)

```bash
./scripts/start-all.sh
./scripts/status-all.sh
./scripts/stop-all.sh
./scripts/stop-all.sh --keep-ollama
```

`start-all.sh` inicia Ollama, espera su API, arranca el simulador, los monitores
de alertas, el servidor TTS y precarga el modelo. `stop-all.sh` detiene todo en
orden inverso, incluido Ollama salvo que se use `--keep-ollama`. En la placa:
`~/start-can.sh`, `~/status-can.sh` y `~/stop-can.sh`. Si los servicios systemd
están activos, los scripts detectan el PID y no duplican procesos.

### Logger CAN (requiere `can0`)

```bash
sudo ./scripts/install-service.sh
sudo systemctl start jarvis-can-logger
```

Sin hardware CAN, el servicio queda habilitado pero no puede abrir `can0`.
El simulador Python es la alternativa para pruebas.

### Simulador, alertas y consultas

```bash
./scripts/start-all.sh               # sistema completo (Ollama, simulador, alertas, TTS)
./scripts/start-can-demo.sh          # alternativa: simulador + monitores
./scripts/status-can-demo.sh
./scripts/status-alerts.sh
./scripts/ask-can.sh "¿Cuál fue la velocidad máxima en la última hora?"
./scripts/stop-can-demo.sh
```

`CAN_DEMO_ALERTS=0 ./scripts/start-can-demo.sh` arranca solo el simulador.
Para el servicio persistente de alertas se recomienda `install-all-services.sh`;
`install-alerts-service.sh` queda como instalación individual de solo alertas.

### Panel de alertas

El panel corre como `jarvis-can-tts` y queda disponible en:

| Acceso | URL |
|---|---|
| Vía router demo | **http://192.168.10.1:8090/** |
| Directo a la placa | http://192.168.10.75:8090/ |

Para control manual del panel:

```bash
./scripts/start-tts.sh
./scripts/status-tts.sh
```

Tocar **Activar sonido** una vez y dejar la página abierta. El panel muestra la
regla detectada, la hora y el mensaje de cada alerta, y reproduce el audio en
el navegador del visitante. No captura micrófono; no hace falta audífono
Bluetooth.

## 7. Verificación rápida

```bash
systemctl is-active jarvis-can-sim jarvis-can-alerts jarvis-can-tts
./scripts/build.sh
./scripts/start-can-demo.sh
sleep 65
./scripts/status-can-demo.sh
./scripts/status-alerts.sh
./scripts/can_alerts.py --once --dry-run
./scripts/ask-can.sh "¿Cuál fue la velocidad máxima en la última hora?"
./scripts/voice-can.sh --tts-test "Hola, soy Jarvis."
./scripts/voice-can.sh --query "¿Cuál es la velocidad en la última hora?"
./scripts/start-tts.sh
curl -fsS http://127.0.0.1:8090/healthz
curl -fsS "http://127.0.0.1:8090/api/alerts?limit=3"
```

## 8. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `can_logger` no abre `can0` | No hay hardware CAN ni módulo `vcan` | Usar el simulador; ver `HARDWARE.md` |
| `ask-can.sh` tarda mucho | Modelo frío o RAM justa | Esperar la primera carga; usar 0.5B |
| Vosk no transcribe | IP Webcam detenido o micrófono lejos | Reiniciar IP Webcam; hablar cerca |
| La página no reproduce | Falta tocar **Activar sonido** | Tocar el botón; mantener la página abierta |
| `Piper no está instalado` | Falta `vendor/piper/piper` | `./scripts/install-piper.sh` |
| No existe el modelo Piper | Falta el `.onnx` | `./scripts/install-piper.sh --force` |
| `espeak-ng` no existe | Falta el respaldo | `sudo apt-get install espeak-ng` |
| El TTS no se oye en la placa | Salida de audio no utilizable | Usar la página en teléfono/PC |
| No hay alertas | Simulador detenido o base sin anomalías | Revisar `status-alerts.sh` y `data/alerts.log` |
| El panel no muestra alertas nuevas | Aún no se cumplió una regla | Esperar el chequeo o probar `can_alerts.py --once --dry-run` |
| Las alertas hablan todas juntas | Se ejecutó `--once` | En modo normal respetar `--initial-gap 300` |

## 9. Seguridad

- Todo el procesamiento es local: Vosk, Ollama y Piper (o espeak-ng).
- Ollama escucha solo en `127.0.0.1`.
- El panel de alertas escucha en `0.0.0.0:8090` para que el teléfono o la PC
  de la misma red puedan abrir la página; no se expone a Internet.
- En la demo, el router OpenWrt publica el 8090 y el 8001 de la placa mediante
  DNAT. Esas reglas solo deben estar activas durante la demo y en una red de
  confianza.
- No se versionan bases, modelos, `.pylibs`, WAV, logs, PID, binarios ni
  credenciales.
