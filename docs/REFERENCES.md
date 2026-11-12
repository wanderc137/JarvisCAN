# Referencias — JarvisCAN

> Enlaces oficiales y comunitarios usados para diseñar, implementar y documentar el proyecto.
> Última revisión: **2026-11-12**. Los enlaces pueden cambiar; se listan por su utilidad, no por afiliación.

---

## 1. OBD-II, CAN y diagnóstico automotriz

| Recurso | URL | Para qué sirve |
|---|---|---|
| OBD-II PIDs — Wikipedia | <https://en.wikipedia.org/wiki/OBD-II_PIDs> | Catálogo de PIDs, fórmulas de conversión y unidades; base del logger. |
| SocketCAN — kernel.org | <https://www.kernel.org/doc/html/latest/networking/can.html> | API CAN de Linux (`PF_CAN`, `SOCK_RAW`, `can0`) usada por `obd.c`. |
| SocketCAN — Wikipedia | <https://en.wikipedia.org/wiki/SocketCAN> | Introducción histórica y conceptual al stack CAN de Linux. |
| can-utils | <https://github.com/linux-can/can-utils> | `candump`, `cansend`, `canbusload`; diagnóstico del bus. |
| ISO 15765-4 | <https://www.iso.org/standard/66349.html> | Diagnóstico sobre CAN (OBD-II); define tramas y direcciones. |
| ISO 11898-2 | <https://www.iso.org/standard/63648.html> | Capa física CAN de alta velocidad; terminación y niveles diferenciales. |
| CAN in Automation (CiA) | <https://www.can-cia.org/> | Asociación de fabricantes; especificaciones y formación sobre CAN. |
| CSS Electronics — OBD2 | <https://www.csselectronics.com/pages/obd2-explained-simple-intro> | Explicación práctica de OBD-II, PIDs y modos de diagnóstico. |

---

## 2. Arduino UNO Q y plataforma

| Recurso | URL | Para qué sirve |
|---|---|---|
| Arduino | <https://www.arduino.cc/> | Plataforma, productos y descargas. |
| Documentación Arduino | <https://docs.arduino.cc/> | Guías de hardware y software. |
| Arduino UNO Q | <https://docs.arduino.cc/hardware/uno-q/> | Documentación de la placa usada (MPU Linux + MCU STM32U585). |
| Foro Arduino | <https://forum.arduino.cc/> | Comunidad; casos de audio, Linux y periféricos. |
| Debian | <https://www.debian.org/doc/> | Base del SO de la placa; administración y paquetes. |

---

## 3. SQLite

| Recurso | URL | Para qué sirve |
|---|---|---|
| SQLite — documentación | <https://sqlite.org/docs.html> | Referencia oficial de SQL, API C y herramientas. |
| WAL | <https://sqlite.org/wal.html> | Modo de registro usado para lecturas concurrentes. |
| PRAGMAs | <https://sqlite.org/pragma.html> | Ajustes de `busy_timeout`, `synchronous`, `journal_mode`. |
| API C | <https://sqlite.org/c3ref/intro.html> | `sqlite3_open_v2`, `prepare`, `bind`, `step`. |
| Backup API | <https://sqlite.org/backup.html> | Copias consistentes con la base en uso. |

---

## 4. systemd y operación en Linux

| Recurso | URL | Para qué sirve |
|---|---|---|
| systemd | <https://systemd.io/> | Proyecto y documentación general. |
| `systemd.service` | <https://www.freedesktop.org/software/systemd/man/systemd.service.html> | Directivas de unidad: `ExecStart`, `Restart`, `ExecStopPost`. |
| `journalctl` | <https://www.freedesktop.org/software/systemd/man/journalctl.html> | Consulta de logs de los servicios. |
| `systemctl` | <https://www.freedesktop.org/software/systemd/man/systemctl.html> | Habilitar, iniciar y revisar unidades. |
| Sudoers | <https://www.sudo.ws/docs/man/sudoers.man/> | Regla acotada de `NOPASSWD` para el logger. |

---

## 5. Voz: Piper, espeak-ng y Vosk

| Recurso | URL | Para qué sirve |
|---|---|---|
| Piper | <https://github.com/rhasspy/piper> | TTS neuronal local usado para las alertas. |
| Voces Piper | <https://huggingface.co/rhasspy/piper-voices> | Modelos `.onnx` en español (`es_MX`, `es_ES`, `es_AR`). |
| Piper — documentación | <https://github.com/rhasspy/piper/blob/master/README.md> | Instalación, CLI y formato de entrada. |
| espeak-ng | <https://github.com/espeak-ng/espeak-ng> | Sintetizador de respaldo; rápido y robótico. |
| Vosk | <https://alphacephei.com/vosk/> | Reconocimiento de voz offline; entrada opcional. |
| Vosk API | <https://github.com/alphacep/vosk-api> | Bindings Python y modelos pequeños en español. |
| IP Webcam | <https://play.google.com/store/apps/details?id=com.pas.webcam> | App Android usada como micrófono de red (WAV 44,1 kHz). |

---

## 6. LLM local: Ollama y Qwen

| Recurso | URL | Para qué sirve |
|---|---|---|
| Ollama | <https://ollama.com/> | Ejecución local de modelos; API en `127.0.0.1:11434`. |
| Ollama — GitHub | <https://github.com/ollama/ollama> | Instalación, API y solución de problemas. |
| Qwen2.5 | <https://github.com/QwenLM/Qwen2.5> | Familia de modelos; versión 0.5B usada para enrutar. |
| Qwen2.5 en Ollama | <https://ollama.com/library/qwen2.5> | Variantes y tamaños disponibles. |

---

## 7. Red, firewall y demo

| Recurso | URL | Para qué sirve |
|---|---|---|
| OpenWrt — firewall | <https://openwrt.org/docs/guide-user/firewall/firewall_configuration> | DNAT, SNAT y reglas usadas en el router de demo. |
| OpenWrt — DNAT | <https://openwrt.org/docs/guide-user/firewall/firewall_configuration#dnat> | Publicación del puerto 8090 en la LAN. |
| nftables | <https://wiki.nftables.org/wiki-nftables/index.php/Main_Page> | Motor de filtrado subyacente en sistemas modernos. |
| RFC 1918 | <https://datatracker.ietf.org/doc/html/rfc1918> | Direcciones privadas usadas en la demo (`192.168.x.x`). |
| Mermaid | <https://mermaid.js.org/> | Diagramas del README y de la documentación. |
| Shields.io | <https://shields.io/> | Badges del encabezado. |

---

## 8. Lecturas recomendadas

| Tema | Recurso | Por qué |
|---|---|---|
| Diagnóstico a bordo | SAE J1979 | Norma de PIDs y modos OBD-II; complementa la tabla de Wikipedia. |
| Bus CAN | “CAN bus explained” de CSS Electronics | Introducción práctica a tramas, arbitraje y terminación. |
| SQLite a escala | “Appropriate Uses For SQLite” (sqlite.org) | Confirma cuándo SQLite es la elección correcta. |
| TTS local | Documentación de Piper y voces | Comparar latencia y calidad antes de cambiar de voz. |
| LLM pequeño | Qwen2.5 0.5B | Entender límites de enrutamiento y necesidad de validación. |

---

## 9. Nota sobre el estado del hardware

Los enlaces de Arduino y CAN describen la plataforma y el protocolo, **no** una integración ya resuelta. En este proyecto:

- La UNO Q no expone `can0`.
- No hay transceptor conectado al bus del Versa.
- Los datos de la base son simulados (`source=can_sim`).

Cualquier afirmación de adquisición real debe esperar a la validación con un adaptador USB-CAN o un transceptor 3,3 V con firmware de puente. Ver [`HARDWARE.md`](HARDWARE.md).
