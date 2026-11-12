# Consultas y métricas

JarvisCAN guarda una fila por muestra en la tabla única `vehicle_samples`.
Las consultas se hacen con el binario C `bin/can_query`; el asistente en
lenguaje natural `scripts/jarvis-can-ask.py` arma esos parámetros a partir de
una pregunta en español.

## 1. Métricas disponibles

| Métrica | Etiqueta | Unidad |
|---|---|---|
| `speed_kph` | Velocidad | km/h |
| `rpm` | RPM | rpm |
| `coolant_c` | Temperatura del refrigerante | °C |
| `engine_load_pct` | Carga del motor | % |
| `throttle_pct` | Acelerador | % |
| `fuel_level_pct` | Nivel de combustible | % |
| `intake_air_c` | Temperatura del aire de admisión | °C |
| `maf_gps` | MAF | g/s |
| `fuel_pressure_kpa` | Presión de combustible | kPa |
| `map_kpa` | MAP (presión del colector) | kPa |
| `timing_advance_deg` | Avance de encendido | ° |
| `run_time_s` | Tiempo de motor | s |
| `battery_v` | Voltaje de batería | V |
| `oil_temp_c` | Temperatura del aceite | °C |
| `barometric_kpa` | Presión barométrica | kPa |
| `short_fuel_trim_pct` | STFT | % |
| `long_fuel_trim_pct` | LTFT | % |
| `catalyst_temp_c` | Temperatura del catalizador | °C |
| `ambient_air_c` | Temperatura ambiente | °C |
| `coolant_level_pct` | Nivel de refrigerante | % |
| `oil_level_pct` | Nivel de aceite | % |
| `tire_fl_kpa` | Presión neumático delantero izquierdo | kPa |
| `tire_fr_kpa` | Presión neumático delantero derecho | kPa |
| `tire_rl_kpa` | Presión neumático trasero izquierdo | kPa |
| `tire_rr_kpa` | Presión neumático trasero derecho | kPa |

Los códigos `dtc_codes` y los avisos `warning_flags` no se consultan como
métrica individual; aparecen en `--metric all` y en `--metric raw`.

También se aceptan:

- `--metric all`: todas las columnas.
- `--metric raw`: la muestra cruda (`raw_json`).
- `--list-metrics`: imprime la tabla anterior.

## 2. `can_query`

```text
can_query [opciones]
```

| Opción | Valores | Descripción |
|---|---|---|
| `--db` | ruta | Base SQLite (default `data/vehicle.db`) |
| `--metric` | nombre, `all`, `raw` | Métrica a consultar |
| `--agg` | `none`, `avg`, `min`, `max`, `sum`, `count` | Agregación |
| `--from` | `now`, `today`, `-60s`, `-60m`, `-24h`, `-7d`, ISO | Inicio |
| `--to` | igual que `--from` | Fin |
| `--last` | entero | Últimas N muestras |
| `--limit` | entero | Límite de filas |
| `--order` | `asc`, `desc` | Orden por epoch |
| `--format` | `json`, `csv`, `table` | Salida |
| `--list-metrics` | — | Lista métricas |

La salida JSON tiene la forma:

```json
{
  "query": {"metric": "speed_kph", "agg": "max", "from": "-60m"},
  "columns": ["value"],
  "rows": [{"value": 85.0}],
  "row_count": 1
}
```

`can_query` abre la base en modo solo lectura y solo acepta identificadores de
su lista blanca; no concatena texto arbitrario del usuario en el SQL.

## 3. Ejemplos

```bash
# Últimas muestras
./bin/can_query --last 5 --limit 5 --format table

# Máximo de velocidad en la última hora
./bin/can_query --metric speed_kph --agg max --from -60m --format json

# Promedio de RPM de hoy
./bin/can_query --metric rpm --agg avg --from today --format table

# Mínimo de refrigerante en 24 horas
./bin/can_query --metric coolant_c --agg min --from -24h --format json

# Cantidad de muestras
./bin/can_query --metric all --agg count --from today --format json

# Últimas 3 muestras de velocidad, más nuevas primero
./bin/can_query --metric speed_kph --last 3 --limit 3 --order desc --format table

# Nivel de refrigerante y de aceite
./bin/can_query --metric coolant_level_pct --last 5 --limit 5 --format table
./bin/can_query --metric oil_level_pct --agg min --from today --format json

# Presión de cada neumático
./bin/can_query --metric tire_fl_kpa --last 3 --limit 3 --format table
./bin/can_query --metric tire_fr_kpa --agg min --from today --format json

# Muestra cruda (incluye DTC y warnings)
./bin/can_query --metric raw --last 1 --limit 1 --format json
```

Para reglas de alerta, anomalías y avisos por voz ver
[ALERTS.md](ALERTS.md).

## 4. Asistente en lenguaje natural

```bash
./scripts/ask-can.sh "¿Cuál fue la velocidad máxima en la última hora?"
./scripts/ask-can.sh "¿Cuántas muestras hay hoy?"
./scripts/ask-can.sh "Promedio de RPM en la última hora"
./scripts/ask-can.sh "Temperatura máxima del refrigerante de hoy"
./scripts/ask-can.sh "¿Cuál es el nivel de refrigerante en la última hora?"
./scripts/ask-can.sh "¿Cuál es la presión del neumático delantero izquierdo hoy?"
```

Sin argumentos entra en modo interactivo (`vos>`).

Opciones de `jarvis-can-ask.py`:

| Opción | Descripción |
|---|---|
| `--db` | Base SQLite |
| `--query-bin` | Ruta a `can_query` |
| `--ollama` | URL de Ollama (default `http://127.0.0.1:11434`) |
| `--model` | Modelo (default `qwen2.5:0.5b-instruct-q4_K_M`) |
| `--timeout` | Timeout de la petición a Ollama |
| `--show-query` | Muestra la ruta y la tabla |
| `--json` | Devuelve el JSON completo |

El asistente:

1. normaliza acentos y mayúsculas;
2. pide a Ollama un JSON `{metric, agg, from, to, limit, order}`;
3. aplica pistas por palabras clave (máximo, mínimo, promedio, cantidad,
   hoy, última hora, 24 h, 7 días, últimos N, ascendente/descendente);
4. ejecuta `can_query`;
5. arma un resumen determinista en español con los valores exactos.

El resumen no lo escribe el modelo: se construye con los datos de SQLite para
evitar que invente cifras.

## 5. Frases que reconoce

- **Agregación**: máximo, mínimo, promedio, suma, cantidad.
- **Tiempo**: hoy, última hora, últimas 24 horas, últimos 7 días.
- **Filas**: últimos N, últimas N muestras.
- **Orden**: ascendente, descendente.
- **Métricas**: velocidad, RPM, refrigerante, carga del motor, acelerador,
  nivel de combustible, aire de admisión, MAF, presión de combustible, MAP,
  avance de encendido, tiempo de motor, batería, aceite, presión barométrica,
  STFT, LTFT, catalizador, temperatura ambiente.

## 6. Limitaciones

- El logger real usa OBD-II de 11 bits y tramas single-frame; no implementa
  multi-frame ni CAN de 29 bits.
- No hay DBC ni mensajes propietarios del Nissan Versa; solo PIDs OBD-II.
- El simulador no habla con el bus físico: inserta valores ficticios
  directamente en SQLite.
- La base contiene datos de simulación (`source=simulator`) hasta que se
  conecte hardware CAN real.
