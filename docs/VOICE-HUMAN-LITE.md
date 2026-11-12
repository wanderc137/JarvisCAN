# Voz human-lite de JarvisCAN

JarvisCAN 2.0 es la versión única del proyecto. La versión 1 fue retirada:
su carpeta local, su instalación en la placa y su contenido en GitHub fueron
reemplazados por esta versión. Ya no hay dos servidores ni dos bases en
paralelo.

La síntesis usa **Piper TTS** con la voz `es_MX-claude-high` y el perfil
**`human-lite`** por defecto. Es una voz más natural que `flat`, pero sin la
latencia del perfil `human` en esta CPU.

## 1. Estado actual

| Elemento | Valor |
|---|---|
| Carpeta local | `proyectos/JarvisCAN` |
| Carpeta en la placa | `/home/arduino/JarvisCAN` |
| Panel de alertas (web) | `http://192.168.10.1:8090/` (router demo) o `http://192.168.10.75:8090/` |
| Muestras A/B | `http://192.168.10.75:8092/` (temporal) |
| Servicios | `jarvis-can-sim`, `jarvis-can-alerts`, `jarvis-can-tts` (enabled) |
| Repositorio | privado `wanderc137/JarvisCAN` |
| Base SQLite | `data/vehicle.db` (la más reciente, 436 muestras al migrar) |
| Motor por defecto | Piper + `es_MX-claude-high` + `human-lite` |
| Fallback | `espeak-ng` (`--tts-engine espeak`) |

La V1 no se conserva como instalación activa. Para comparar voces no hace
falta volver a la V1: se puede cambiar solo el perfil o el modelo de Piper.

## 2. Perfiles de voz

`scripts/voice-can.py` define tres perfiles:

| Perfil | Comportamiento | Uso |
|---|---|---|
| `flat` | Una sola llamada a Piper, sin ajustes extra | Referencia y máxima velocidad |
| `human` | Divide por frases y varía duración/ruido; concatena con pausas | Más expresivo, más lento |
| `human-lite` | Una sola llamada con pausa de 0,45 s, `noise_w` 0,90 y `length_scale` 1,02 | **Default actual** |

Valores por defecto (se pueden cambiar por entorno):

| Variable | Default |
|---|---|
| `JARVIS_TTS_ENGINE` | `auto` |
| `JARVIS_TTS_PROFILE` | `human-lite` |
| `JARVIS_TTS_LENGTH_SCALE` | `1.02` |
| `JARVIS_TTS_NOISE_SCALE` | `0.667` |
| `JARVIS_TTS_NOISE_W` | `0.90` |
| `JARVIS_TTS_SENTENCE_SILENCE` | `0.45` |

El texto hablado omite el timestamp ISO entre paréntesis, pero lo conserva en
el texto de la respuesta. El perfil `human` además normaliza `;` y `:` para
mejorar la prosodia.

Opciones útiles:

```bash
--tts-profile flat|human|human-lite
--tts-engine auto|piper|espeak
--tts-model /ruta/al/modelo.onnx
--tts-length-scale 1.02
--tts-noise-scale 0.667
--tts-noise-w 0.90
--tts-sentence-silence 0.45
--play-audio auto|on|off
--sink ID|nombre
```

`data/last_answer.json` incluye `tts_engine`, `tts_profile`, `tts_model`,
`played_on_device` y `audio_sink`.

## 3. Benchmarks reales

Misma frase de dos oraciones, CPU-only, 4× Cortex-A53. `wall` incluye cargar
Piper y sintetizar; `audio` es la duración del WAV.

| Voz | Perfil | wall | audio |
|---|---|---:|---:|
| `es_MX-claude-high` | flat | 8,76 s | 7,99 s |
| `es_MX-claude-high` | human | 13,47 s | 7,84 s |
| `es_MX-claude-high` | human-lite | 8,93 s | 8,20 s |
| `es_ES-davefx-medium` | flat | 5,46 s | 7,07 s |
| `es_ES-davefx-medium` | human | 8,29 s | 6,71 s |
| `es_AR-daniela-high` | human | 37,50 s | 5,97 s |

Segunda corrida de `tts-compare.sh`: `human-lite` de MX midió 8,38 s de pared
y 8,37 s de audio.

Prueba final con el default ya desplegado:

- `--tts-test`: 9,2 s de pared, WAV de 8,39 s.
- Consulta completa: 45,65 s en frío (incluye la primera carga del LLM),
  WAV de 7,66 s, reproducida en `EW02 Plus` (`played_on_device: true`,
  `tts_profile: human-lite`).

## 4. Uso normal

```bash
# Los tres servicios arrancan solos con la placa; control manual opcional:
~/start-can.sh     # Ollama + simulador + alertas + TTS en 8090
~/status-can.sh
~/stop-can.sh

cd ~/JarvisCAN
./scripts/ask-can.sh "¿Cuál es la velocidad en la última hora?"
./scripts/voice-can.sh --tts-test "Probando la voz human-lite de JarvisCAN." --play-audio on
```

El panel de alertas queda en:

```text
http://192.168.10.1:8090/
```

Muestra la regla detectada, la hora y el mensaje de cada alerta, y reproduce el
audio automáticamente después de tocar **Activar sonido**. No captura micrófono.

Para una consulta por texto con la voz por defecto:

```bash
./scripts/voice-can.sh --query "¿Cuál es la velocidad en la última hora?" --play-audio auto
```

## 5. Generar y escuchar muestras

```bash
cd ~/JarvisCAN

# Genera/actualiza las muestras flat, human y human-lite para MX y davefx
./scripts/tts-compare.sh

# Publica la página de comparación en el puerto 8092
./scripts/serve-tts-samples.sh
```

Abrir en el teléfono o en la PC:

```text
http://192.168.10.75:8092/
```

Para incluir también `es_AR-daniela-high`:

```bash
TTS_COMPARE_ALL=1 ./scripts/tts-compare.sh
```

Para detener el servidor de muestras:

```bash
./scripts/serve-tts-samples.sh --stop
```

Las muestras quedan en `data/tts-samples/` y están excluidas de git. El
servidor de muestras es HTTP sin autenticación y solo debe usarse en la LAN.

## 6. Ajustes

- Si la voz suena demasiado lenta, bajar `JARVIS_TTS_LENGTH_SCALE` a `1.0` o
  usar `--tts-profile flat`.
- Si suena entrecortada, subir `JARVIS_TTS_SENTENCE_SILENCE` a `0.55` o `0.60`.
- Si suena monótona, probar `--tts-profile human` y medir la latencia.
- Para cambiar de voz sin tocar código:
  `--tts-model models/piper/es_ES-davefx-medium.onnx`.
- Para volver a espeak-ng: `--tts-engine espeak`.

## 7. Próximo paso posible: Kokoro

Kokoro-82M ONNX podría dar una prosodia mejor que Piper, pero hay que medirlo en
esta CPU. No está instalado ni descargado. Antes de instalarlo hace falta
autorización explícita del usuario.

Plan tentativo:

1. Medir tamaño, RAM y latencia de Kokoro en la placa.
2. Generar las mismas frases y comparar A/B contra `es_MX-claude-high`.
3. Si mejora sin arruinar la latencia, integrarlo como motor alternativo
   (`--tts-engine kokoro`) manteniendo Piper como fallback.
4. Si no convence, quedarse con Piper `human-lite` y descartar Kokoro.

## 8. Limitaciones

- No hay GPU: la síntesis es más lenta que en una PC.
- `human-lite` es el default; `human` tarda más porque hace varias llamadas a
  Piper.
- Piper no es una voz emocional de nivel comercial; mejora la cadencia, no la
  convierte en una locutora humana.
- La V1 fue eliminada; no hay rollback a esa instalación. Sí se puede cambiar
  de perfil de voz o de modelo Piper.
- No hay CAN real; la base sigue siendo simulada.
- La salida de audio interna de la UNO Q no funciona; se usa el audífono
  Bluetooth EW02 Plus o el navegador del teléfono/PC.
