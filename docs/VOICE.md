> **Nota 2026-11-11:** la página 8090 es un **panel de alertas sin micrófono**.
> Corre como servicio systemd (`jarvis-can-tts`) y se publica en
> `http://192.168.10.1:8090/` (router demo) o `http://192.168.10.75:8090/`.
> El modo de voz por IP Webcam sigue disponible por terminal
> (`voice-can-cam.sh`), pero no se usa desde el panel. Ver
> [VOICE-HUMAN-LITE.md](VOICE-HUMAN-LITE.md).

# Voz: micrófono IP Webcam y respuesta TTS

JarvisCAN acepta preguntas habladas en español y responde por voz. Todo el
procesamiento es local: Vosk transcribe, Ollama interpreta, `can_query`
consulta SQLite y Piper TTS genera el audio (con espeak-ng como respaldo). La única dependencia de red es la
WiFi local entre el teléfono y la UNO Q.

La voz por defecto es `es_MX-claude-high` con el perfil **`human-lite`**
(pausa de 0,45 s, `noise_w` 0,90 y `length_scale` 1,02). Los perfiles y
benchmarks están en [VOICE-HUMAN-LITE.md](VOICE-HUMAN-LITE.md).

## 1. Arquitectura de voz

```text
Teléfono (IP Webcam)                         UNO Q
  /audio.wav  --- WiFi --->  voice-can.py (Vosk 16 kHz)
                                      |
                                      v
                             jarvis-can-ask.py (Ollama)
                                      |
                                      v
                             can_query (C) -> SQLite
                                      |
                                      v
                             Piper TTS -> data/last_answer.wav
                             (fallback espeak-ng)
                                      |
                                      v
                             tts-server.py :8090
                                      |
                    +-----------------+-----------------+
                    |                                   |
          audífono Bluetooth EW02 Plus        navegador teléfono/PC
          (salida principal de la UNO Q)      (respaldo si no hay BT)
```

La UNO Q **no tiene salida de audio interna utilizable**: el jack/parlante
interno no funciona con ALSA ni PipeWire. En cambio, el audífono Bluetooth
**EW02 Plus** sí funciona como sink A2DP. Si está encendido y conectado,
`voice-can.py` reproduce la respuesta directamente en él; si no, el WAV se
sirve por HTTP y lo reproduce el navegador del teléfono o de la PC.

## 2. Micrófono: IP Webcam

App usada: **IP Webcam** (Android), servidor en el teléfono.

1. Abrir IP Webcam y tocar **Start server**.
2. Dejar la app en primer plano y la pantalla encendida.
3. Verificar desde la placa:

```bash
curl -sI http://192.168.1.198:8080/audio.wav | head
```

Debe devolver `HTTP/1.1 200 OK` y `Content-Type: audio/x-wav`.

Endpoints útiles:

| Ruta | Contenido |
|---|---|
| `/video` | MJPEG (no usado por JarvisCAN) |
| `/audio.wav` | WAV 44.100 Hz, mono, 16 bits |
| `/audio.aac` | AAC |
| `/audio.opus` | Opus |

El script `voice-can.py`:

- lee el WAV por HTTP;
- hace downmix a mono si hace falta;
- remuestrea de 44,1 kHz a 16 kHz con interpolación lineal;
- normaliza la ganancia hasta 4× (pico objetivo 26000);
- entrega PCM a Vosk (`vosk-model-small-es-0.42`).

La IP del teléfono se puede cambiar sin editar el código:

```bash
export JARVIS_CAM_AUDIO_URL=http://NUEVA_IP:8080/audio.wav
```

## 3. Uso rápido

En la placa:

```bash
cd ~/JarvisCAN
./scripts/start-tts.sh
```

El panel ya corre como servicio systemd (`jarvis-can-tts`) con autoarranque;
`start-tts.sh` es solo para control manual si el servicio está detenido.

Abrir en el teléfono o en la PC:

```text
http://192.168.10.1:8090/
```

1. Tocar **Activar sonido** (desbloquea el audio del navegador).
2. Dejar la página abierta: muestra cada alerta con su regla y mensaje y
   reproduce el audio automáticamente.
3. No se usa micrófono desde la página.

También se puede lanzar una consulta desde la terminal:

```bash
./scripts/voice-can-cam.sh --auto --once --duration 8
```

o una consulta de texto que también genera TTS:

```bash
./scripts/voice-can.sh --query "¿Cuál fue la velocidad máxima en la última hora?"
```

## 4. Página web y endpoints

`scripts/tts-server.py` sirve en el puerto **8090**:

| Método | Ruta | Función |
|---|---|---|
| GET | `/` | Panel de alertas (texto + audio) |
| GET | `/api/alerts?limit=60` | Alertas recientes y `monitor_active` |
| GET | `/alert-audio/<archivo>` | WAV archivado de una alerta |
| GET | `/healthz` | `{"ok":true}` |
| GET | `/answer.json` | Última respuesta y `mtime` |
| GET | `/answer.wav` | WAV de la última respuesta |
| GET | `/silence.wav` | Silencio para desbloquear el audio |

El panel **no captura micrófono**: no usa `/listen` ni ejecuta
`voice-can-cam.sh`. La entrada por voz queda como utilidad de terminal:

```bash
./scripts/voice-can-cam.sh --auto --once --duration 8
```

`voice-can-cam.sh` arranca el panel si hace falta y usa
`JARVIS_CAM_AUDIO_URL` (por defecto `http://192.168.1.198:8080/audio.wav`).

Scripts de control:

```bash
./scripts/start-tts.sh
./scripts/status-tts.sh
./scripts/stop-tts.sh
```

La IP que se muestra se obtiene de la ruta por defecto (`ip route get
1.1.1.1`), no de `hostname -I`, para evitar la IP de Docker.

## 5. TTS: Piper (con fallback espeak-ng)

`voice-can.py` genera:

```text
data/last_answer.wav
data/last_answer.json
```

El WAV es PCM mono a 22.050 Hz. El JSON contiene `mtime`, `ts`, `text`,
`played_on_device` y `audio_sink`. Si hay un audífono Bluetooth conectado,
`voice-can.py` lo reproduce desde la UNO Q y la página no lo duplica; si no,
la página lo reproduce en el teléfono o en la PC. El timestamp ISO entre
paréntesis se omite al hablar, pero se conserva en el texto.

El motor por defecto es **Piper TTS** con la voz `es_MX-claude-high`
(latinoamericana, alta calidad). Instalación o reinstalación:

```bash
./scripts/install-piper.sh
```

El script descarga el binario ARM64 y la voz dentro del proyecto (unos
90 MB en total):

- binario y librerías: `vendor/piper/`
- modelo: `models/piper/es_MX-claude-high.onnx`

Ninguno de esos archivos se versiona. Voces alternativas:

```bash
./scripts/install-piper.sh --voice es_ES-davefx-medium
./scripts/install-piper.sh --voice es_AR-daniela-high
```

Prueba de síntesis sin micrófono:

```bash
./scripts/voice-can.sh --tts-test "Hola, soy Jarvis."
```

Reproducción por Bluetooth:

```bash
./scripts/voice-can.sh --query "..." --play-audio auto   # default
./scripts/voice-can.sh --query "..." --play-audio on     # exige audífono
./scripts/voice-can.sh --query "..." --play-audio off    # solo genera WAV
```

`--sink ID|nombre` permite elegir explícitamente un sink de PipeWire. En
modo `auto`, si no hay sink Bluetooth, se omite la reproducción y la página
queda como respaldo.

Consulta completa:

```bash
./scripts/voice-can.sh --query "¿Cuál fue la velocidad máxima en la última hora?"
```

Opciones:

```bash
--tts-engine auto|piper|espeak
--tts-model models/piper/es_MX-claude-high.onnx
--piper-bin vendor/piper/piper
--tts-length-scale 1.0       # >1 más lento, <1 más rápido
--tts-voice es               # solo para espeak-ng
--tts-speed 150              # solo para espeak-ng
--no-tts
```

Comportamiento:

- `auto`: usa Piper si el binario y el modelo existen; si Piper falla, cae a
  `espeak-ng`.
- `piper`: fuerza Piper; si falta o falla, devuelve error.
- `espeak`: fuerza `espeak-ng` (voz robótica, útil como respaldo).

Rendimiento medido en la UNO Q (4× Cortex-A53, sin GPU):

| Voz | Tiempo de pared | Audio generado |
|---|---:|---:|
| `es_MX-claude-high` | ~8,4 s | ~7,8 s |
| `es_ES-davefx-medium` | ~4,8 s | ~6,1 s |
| `es_AR-daniela-high` | ~23,7 s | ~5,5 s |

Por eso el default es `es_MX-claude-high`: buena calidad y latencia razonable.
La síntesis corre en la placa; con el EW02 Plus conectado, el WAV se reproduce
en el audífono desde la propia UNO Q.

## 6. Hallazgos de audio en la UNO Q

Estas pruebas quedaron documentadas para no repetirlas:

### AirPods

- Modelo: AirPods (MAC y nombre omitidos).
- Salida A2DP: funcionó; se escuchó un tono de 440 Hz.
- Micrófono HFP: **silencio absoluto** en mSBC y CVSD, con la fuente loopback
  y la interna.
- Se probó reiniciar PipeWire/WirePlumber, reconectar y apagar el Bluetooth
  del Mac; el micrófono siguió en cero.
- Decisión: **eliminar los AirPods**; no se usan.

### Micrófono interno

- Tarjeta `ArduinoImolaHPH`; entradas `hw:0,0` a `hw:0,3`.
- `DMIC1_MIXER`, `DMIC2_MIXER`, `ADC1` y `Mic Jack` estaban en `off`.
- Capturas con ALSA y PipeWire dieron silencio, `Invalid argument`,
  `Device or resource busy` o `Input/output error`.
- Decisión: no usar el micrófono interno.

### Salida de audio de la placa

- `aplay -D plughw:0,0` y `plughw:0,1` fallan con
  `pcm_write: write error: Input/output error`.
- `pw-cat --playback` se cuelga; `pw-top` muestra `QUANT 0`, `RATE 0`.
- Se activaron `EAR_RDAC`, `HPHL/HPHR`, `HPHL_RDAC/HPHR_RDAC`, `LO_RDAC`,
  `RX_EAR` y `RX_HPH`; el error persiste.
- Decisión: la respuesta hablada se reproduce en el teléfono o en la PC.

## 7. Audífonos Bluetooth EW02 Plus

El audífono nuevo es un **EW02 Plus**, clase `audio-headset`, con Audio Sink
y Handsfree. Se emparejó, se marcó como `trusted` y quedó conectado. La
batería informada al emparejar fue 90 %.

### Emparejamiento

```bash
bluetoothctl
power on
agent on
default-agent
scan on
pair XX:XX:XX:XX:XX:XX
trust XX:XX:XX:XX:XX:XX
connect XX:XX:XX:XX:XX:XX
```

En esta placa el audio vive en la sesión de PipeWire de `lightdm`
(`/run/user/103`); el usuario `arduino` accede a ella con la regla
`/etc/sudoers.d/90-jarvis-can-audio`, que permite `pw-dump` y `pw-cat` como
`lightdm`. Los sinks y fuentes se listan con:

```bash
XDG_RUNTIME_DIR=/run/user/103 PIPEWIRE_RUNTIME_DIR=/run/user/103 \
  sudo -n -u lightdm --preserve-env=XDG_RUNTIME_DIR,PIPEWIRE_RUNTIME_DIR \
  /usr/bin/pw-dump
```

### Salida verificada

- `pw-cat --playback --target <sink>` reprodujo el WAV de Piper en el EW02
  Plus; el usuario lo escuchó.
- `voice-can.py --tts-test "..." --play-audio on` terminó con
  `played_on_device: true` y `audio_sink: "EW02 Plus"`.
- La síntesis sigue siendo Piper; el audífono solo mejora la salida, no la
  calidad de la voz.
- Si el audífono está apagado o fuera de alcance, `bluetoothctl connect`
  falla con `br-connection-page-timeout` y la página reproduce el audio como
  respaldo. Encendé el audífono y volvé a conectarlo.

### Micrófono del EW02 Plus

No se probó como micrófono. La vía de entrada verificada sigue siendo
**IP Webcam** en el teléfono; no se cambió el diseño de captura.

## 8. Solución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| La página no suena | Audio bloqueado | Tocar **Activar sonido** |
| La página no suena | Página en segundo plano | Dejarla en primer plano |
| El panel no muestra alertas | Aún no se cumplió una regla | Esperar el chequeo; revisar `status-alerts.sh` |
| `No se entendió nada` (CLI de voz) | Voz lejos o ruido | Hablar cerca del teléfono |
| No abre `/audio.wav` | IP Webcam detenido | Tocar **Start server** |
| IP del teléfono cambió | DHCP | Ajustar `JARVIS_CAM_AUDIO_URL` |
| `Piper no está instalado` | Falta `vendor/piper/piper` | `./scripts/install-piper.sh` |
| No existe el modelo Piper | Falta el `.onnx` | `./scripts/install-piper.sh --force` |
| `Piper tardó demasiado` | Frase muy larga o CPU ocupada | Acortar la respuesta o usar `--tts-engine espeak` |
| `espeak-ng no está instalado` | Falta el paquete de respaldo | `sudo apt-get install espeak-ng` |
| El puerto 8090 no responde | TTS detenido | `systemctl status jarvis-can-tts` o `./scripts/start-tts.sh` |
| El TTS se corta | Texto muy largo | Bajar `--max-tokens` o acortar la pregunta |

## 9. Privacidad

- El audio viaja solo por la WiFi local.
- Vosk, Ollama y Piper (o espeak-ng como respaldo) corren en la placa.
- No se envían datos a Internet.
- La base SQLite es local.
- El servidor TTS no tiene autenticación; está pensado para una red doméstica
  de confianza. No exponer el puerto 8090 a Internet.

## 10. Estado verificado

- Fecha: 2026-11-11.
- Micrófono: IP Webcam en `192.168.1.198:8080/audio.wav`.
- Panel de alertas: `http://192.168.10.1:8090/`.
- Prueba real: “¿cuál es la velocidad en la última hora?” → Vosk transcribió,
  JarvisCAN respondió con 20 registros y el más reciente 74 km/h; el WAV se
  reprodujo en el navegador.
- TTS: Piper `es_MX-claude-high` instalado en `models/piper/`; prueba
  `--tts-test` en 8,6 s. Consulta completa en frío: 36 s (Ollama ~27 s +
  Piper ~8,6 s); en caliente baja.
- AirPods eliminados.
- Salida de audio interna de la UNO Q: no utilizable.
- Audífono Bluetooth EW02 Plus: emparejado y salida verificada; si está
  apagado, la página reproduce el audio como respaldo.
- Micrófono del EW02 Plus: no probado; se sigue usando IP Webcam.
