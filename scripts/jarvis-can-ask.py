#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request

METRICS = [
    "speed_kph", "rpm", "coolant_c", "engine_load_pct", "throttle_pct",
    "fuel_level_pct", "intake_air_c", "maf_gps", "fuel_pressure_kpa",
    "map_kpa", "timing_advance_deg", "run_time_s", "battery_v", "oil_temp_c",
    "barometric_kpa", "short_fuel_trim_pct", "long_fuel_trim_pct",
    "catalyst_temp_c", "ambient_air_c", "coolant_level_pct", "oil_level_pct",
    "tire_fl_kpa", "tire_fr_kpa", "tire_rl_kpa", "tire_rr_kpa",
]
AGGS = ["none", "avg", "min", "max", "sum", "count"]

ROUTER_PROMPT = """Sos un traductor de preguntas a consultas de una base de datos de un Nissan Versa 2020.
Devolve SOLO un objeto JSON valido, sin markdown, con esta forma:
{"metric":"speed_kph","agg":"none","from":"-60m","to":"now","limit":20,"order":"desc"}

metric permitido: %s, all.
agg permitido: none, avg, min, max, sum, count.
from/to: now, today, -60m, -24h, -7d o una fecha ISO.
order: asc o desc.
limit: entero entre 1 y 100.
Si la pregunta pide cantidad o cuantos, usa agg count y metric all.
Si pide promedio usa avg; maximo usa max; minimo usa min; suma usa sum.
Si no se entiende, usa metric all, agg none, from -60m, limit 20.
Pregunta: %s"""


def ollama_chat(host, model, messages, timeout, fmt=None, temperature=0.0,
                num_predict=180, num_ctx=2048):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "15m",
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
    }
    if fmt:
        payload["format"] = fmt
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("message", {}).get("content", "")


def normalize_text(text):
    folded = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def fallback_route(question):
    q = normalize_text(question)
    metric = "all"
    for word, name in [
        ("velocidad", "speed_kph"),
        ("rpm", "rpm"),
        ("revolucion", "rpm"),
        ("nivel de refrigerante", "coolant_level_pct"),
        ("nivel del refrigerante", "coolant_level_pct"),
        ("refrigerante", "coolant_c"),
        ("temperatura del motor", "coolant_c"),
        ("nivel de aceite", "oil_level_pct"),
        ("nivel del aceite", "oil_level_pct"),
        ("aceite", "oil_temp_c"),
        ("presion de neumatico delantero izquierdo", "tire_fl_kpa"),
        ("presion del neumatico delantero izquierdo", "tire_fl_kpa"),
        ("presion de neumatico delantero derecho", "tire_fr_kpa"),
        ("presion del neumatico delantero derecho", "tire_fr_kpa"),
        ("presion de neumatico trasero izquierdo", "tire_rl_kpa"),
        ("presion del neumatico trasero izquierdo", "tire_rl_kpa"),
        ("presion de neumatico trasero derecho", "tire_rr_kpa"),
        ("presion del neumatico trasero derecho", "tire_rr_kpa"),
        ("rueda delantera izquierda", "tire_fl_kpa"),
        ("rueda delantera derecha", "tire_fr_kpa"),
        ("rueda trasera izquierda", "tire_rl_kpa"),
        ("rueda trasera derecha", "tire_rr_kpa"),
        ("presion de combustible", "fuel_pressure_kpa"),
        ("presion del combustible", "fuel_pressure_kpa"),
        ("nivel de combustible", "fuel_level_pct"),
        ("nivel del combustible", "fuel_level_pct"),
        ("combustible", "fuel_level_pct"),
        ("nafta", "fuel_level_pct"),
        ("bateria", "battery_v"),
        ("voltaje", "battery_v"),
        ("acelerador", "throttle_pct"),
        ("carga del motor", "engine_load_pct"),
        ("carga motor", "engine_load_pct"),
        ("carga", "engine_load_pct"),
        ("aire de admision", "intake_air_c"),
        ("maf", "maf_gps"),
        ("catalizador", "catalyst_temp_c"),
        ("presion barometrica", "barometric_kpa"),
        ("barometrica", "barometric_kpa"),
        ("presion del colector", "map_kpa"),
        ("presion de admision", "map_kpa"),
        ("colector", "map_kpa"),
        ("map", "map_kpa"),
        ("avance", "timing_advance_deg"),
        ("tiempo de motor", "run_time_s"),
        ("tiempo motor", "run_time_s"),
        ("tiempo encendido", "run_time_s"),
        ("stft", "short_fuel_trim_pct"),
        ("trim corto", "short_fuel_trim_pct"),
        ("ltft", "long_fuel_trim_pct"),
        ("trim largo", "long_fuel_trim_pct"),
        ("temperatura ambiente", "ambient_air_c"),
        ("ambiente", "ambient_air_c"),
        ("presion", "barometric_kpa"),
    ]:
        if word in q:
            metric = name
            break
    agg = "none"
    if "cuant" in q or "cantidad" in q:
        agg = "count"
        metric = "all"
    elif "promedio" in q or "media" in q:
        agg = "avg"
    elif "maxim" in q or "mayor" in q:
        agg = "max"
    elif "minim" in q or "menor" in q:
        agg = "min"
    elif "suma" in q or "total" in q:
        agg = "sum"
    from_value = "-60m"
    if "hoy" in q:
        from_value = "today"
    elif "semana" in q:
        from_value = "-7d"
    elif "24" in q and ("hora" in q or "hs" in q):
        from_value = "-24h"
    elif "ultima hora" in q or "última hora" in q:
        from_value = "-60m"
    limit = 20
    m = re.search(r"ultimos?\s+(\d+)", q)
    if not m:
        m = re.search(r"últimos?\s+(\d+)", q)
    if m:
        limit = max(1, min(100, int(m.group(1))))
    order = "desc"
    if "ascendente" in q or "de menor a mayor" in q:
        order = "asc"
    return {
        "metric": metric,
        "agg": agg,
        "from": from_value,
        "to": "now",
        "limit": limit,
        "order": order,
    }


STRONG_HINTS = [
    ("nivel de refrigerante", "coolant_level_pct"),
    ("nivel del refrigerante", "coolant_level_pct"),
    ("nivel de aceite", "oil_level_pct"),
    ("nivel del aceite", "oil_level_pct"),
    ("presion de neumatico delantero izquierdo", "tire_fl_kpa"),
    ("presion del neumatico delantero izquierdo", "tire_fl_kpa"),
    ("presion de neumatico delantero derecho", "tire_fr_kpa"),
    ("presion del neumatico delantero derecho", "tire_fr_kpa"),
    ("presion de neumatico trasero izquierdo", "tire_rl_kpa"),
    ("presion del neumatico trasero izquierdo", "tire_rl_kpa"),
    ("presion de neumatico trasero derecho", "tire_rr_kpa"),
    ("presion del neumatico trasero derecho", "tire_rr_kpa"),
    ("rueda delantera izquierda", "tire_fl_kpa"),
    ("rueda delantera derecha", "tire_fr_kpa"),
    ("rueda trasera izquierda", "tire_rl_kpa"),
    ("rueda trasera derecha", "tire_rr_kpa"),
]


def apply_question_hints(route, question):
    q = normalize_text(question)
    hints = fallback_route(question)
    if route.get("metric") == "all" and hints["metric"] != "all":
        route["metric"] = hints["metric"]
    for word, name in STRONG_HINTS:
        if word in q:
            route["metric"] = name
            break
    if any(word in q for word in ("maxim", "mayor")):
        route["agg"] = "max"
    elif any(word in q for word in ("minim", "menor")):
        route["agg"] = "min"
    elif any(word in q for word in ("promedio", "media")):
        route["agg"] = "avg"
    elif any(word in q for word in ("cuant", "cantidad")):
        route["agg"] = "count"
        route["metric"] = "all"
    elif any(word in q for word in ("suma", "total")):
        route["agg"] = "sum"
    if "hoy" in q:
        route["from"] = "today"
    elif "semana" in q:
        route["from"] = "-7d"
    elif "24" in q and "hora" in q:
        route["from"] = "-24h"
    elif "ultima hora" in q or "última hora" in q:
        route["from"] = "-60m"
    if "ultimos" in q or "últimos" in q:
        route["limit"] = hints["limit"]
    if "ascendente" in q or "de menor a mayor" in q:
        route["order"] = "asc"
    if route["agg"] == "count":
        route["metric"] = "all"
    return route


def normalize_route(route, question):
    if not isinstance(route, dict):
        return fallback_route(question)
    metric = str(route.get("metric", "all")).strip()
    agg = str(route.get("agg", "none")).strip().lower()
    if metric not in METRICS + ["all"]:
        return fallback_route(question)
    if agg not in AGGS:
        return fallback_route(question)
    if agg != "count" and metric == "all":
        agg = "none"
    from_value = str(route.get("from", "-60m")).strip() or "-60m"
    to_value = str(route.get("to", "now")).strip() or "now"
    if from_value.lower() in ("ultima hora", "última hora"):
        from_value = "-60m"
    if from_value.lower() in ("hoy",):
        from_value = "today"
    try:
        limit = int(route.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(100, limit))
    order = str(route.get("order", "desc")).strip().lower()
    if order not in ("asc", "desc"):
        order = "desc"
    return {
        "metric": metric,
        "agg": agg,
        "from": from_value,
        "to": to_value,
        "limit": limit,
        "order": order,
    }


def route_question(question, host, model, timeout):
    prompt = ROUTER_PROMPT % (", ".join(METRICS), question)
    try:
        content = ollama_chat(
            host, model,
            [
                {"role": "system", "content": "Respondes solo JSON valido."},
                {"role": "user", "content": prompt},
            ],
            timeout=timeout, fmt="json", temperature=0.0, num_predict=140, num_ctx=2048,
        )
        route = json.loads(content)
        return normalize_route(route, question)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
        return fallback_route(question)


def run_query(query_bin, db_path, route):
    cmd = [
        query_bin, "--db", db_path,
        "--metric", route["metric"],
        "--agg", route["agg"],
        "--from", route["from"],
        "--to", route["to"],
        "--limit", str(route["limit"]),
        "--order", route["order"],
        "--format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "fallo can_query")
    return json.loads(proc.stdout)


def format_value(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def table_text(result, max_rows=30):
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    if not columns:
        return "(sin columnas)"
    lines = [" | ".join(columns)]
    for row in rows[:max_rows]:
        lines.append(" | ".join(format_value(row.get(col)) for col in columns))
    if len(rows) > max_rows:
        lines.append(f"... {len(rows) - max_rows} filas mas")
    return "\n".join(lines)


METRIC_INFO = {
    "speed_kph": ("velocidad", "km/h"),
    "rpm": ("las RPM", "rpm"),
    "coolant_c": ("la temperatura del refrigerante", "°C"),
    "engine_load_pct": ("la carga del motor", "%"),
    "throttle_pct": ("la apertura del acelerador", "%"),
    "fuel_level_pct": ("el nivel de combustible", "%"),
    "intake_air_c": ("la temperatura del aire de admisión", "°C"),
    "maf_gps": ("el flujo de aire MAF", "g/s"),
    "fuel_pressure_kpa": ("la presión de combustible", "kPa"),
    "map_kpa": ("la presión del colector MAP", "kPa"),
    "timing_advance_deg": ("el avance de encendido", "°"),
    "run_time_s": ("el tiempo de motor en marcha", "s"),
    "battery_v": ("el voltaje de la batería", "V"),
    "oil_temp_c": ("la temperatura del aceite", "°C"),
    "barometric_kpa": ("la presión barométrica", "kPa"),
    "short_fuel_trim_pct": ("el ajuste corto de combustible", "%"),
    "long_fuel_trim_pct": ("el ajuste largo de combustible", "%"),
    "catalyst_temp_c": ("la temperatura del catalizador", "°C"),
    "ambient_air_c": ("la temperatura ambiente", "°C"),
    "coolant_level_pct": ("el nivel de refrigerante", "%"),
    "oil_level_pct": ("el nivel de aceite", "%"),
    "tire_fl_kpa": ("la presión del neumático delantero izquierdo", "kPa"),
    "tire_fr_kpa": ("la presión del neumático delantero derecho", "kPa"),
    "tire_rl_kpa": ("la presión del neumático trasero izquierdo", "kPa"),
    "tire_rr_kpa": ("la presión del neumático trasero derecho", "kPa"),
}


def of_label(label):
    if label.startswith("el "):
        return "del " + label[3:]
    if label.startswith("los "):
        return "de los " + label[4:]
    if label.startswith("las "):
        return "de las " + label[4:]
    return "de " + label


def period_label(from_value):
    value = str(from_value).lower()
    if value == "today":
        return "hoy"
    if value == "-60m":
        return "en la última hora"
    if value == "-24h":
        return "en las últimas 24 horas"
    if value == "-7d":
        return "en los últimos 7 días"
    return "en el período consultado"


def summarize(question, route, result, host, model, timeout):
    if result.get("row_count", 0) == 0:
        return "No hay datos en la base para esa consulta."
    rows = result.get("rows", [])
    if not rows:
        return "No hay datos en la base para esa consulta."
    agg = route.get("agg", "none")
    period = period_label(route.get("from", ""))
    if agg == "count":
        return f"Hay {int(rows[0].get('n', 0))} muestras {period}."
    metric = route.get("metric", "all")
    if agg in ("max", "min", "avg", "sum") and metric in METRIC_INFO:
        label, unit = METRIC_INFO[metric]
        value = format_value(rows[0].get("value"))
        prefix = {
            "max": "El máximo",
            "min": "El mínimo",
            "avg": "El promedio",
            "sum": "La suma",
        }[agg]
        return f"{prefix} {of_label(label)} {period} fue {value} {unit}."
    if metric in METRIC_INFO and rows:
        label, unit = METRIC_INFO[metric]
        if len(rows) == 1:
            row = rows[0]
            return (
                f"El registro {of_label(label)} {period} es "
                f"{format_value(row.get(metric))} {unit} ({row.get('ts_utc', '-')})."
            )
        row = rows[0]
        return (
            f"Se encontraron {len(rows)} registros {of_label(label)} {period}; "
            f"el más reciente es {format_value(row.get(metric))} {unit} "
            f"({row.get('ts_utc', '-')})."
        )
    return f"Se encontraron {result.get('row_count', len(rows))} registros {period}."


def answer_once(question, args):
    route = route_question(question, args.ollama, args.model, args.timeout)
    route = apply_question_hints(route, question)
    try:
        result = run_query(args.query_bin, args.db, route)
    except RuntimeError:
        route = apply_question_hints(fallback_route(question), question)
        result = run_query(args.query_bin, args.db, route)
    answer = summarize(question, route, result, args.ollama, args.model, args.timeout)
    if args.show_query:
        print("consulta:", json.dumps(route, ensure_ascii=False), file=sys.stderr)
        print(table_text(result), file=sys.stderr)
    if args.json:
        print(json.dumps({"question": question, "route": route, "result": result,
                          "answer": answer}, ensure_ascii=False, indent=2))
    else:
        print(answer)
    return answer


def main():
    parser = argparse.ArgumentParser(description="Preguntas en lenguaje natural sobre la base CAN")
    parser.add_argument("question", nargs="*", help="pregunta; sin argumentos entra en modo interactivo")
    parser.add_argument("--db", default=os.environ.get("JARVIS_CAN_DB", "data/vehicle.db"))
    parser.add_argument("--query-bin", default=os.environ.get("JARVIS_CAN_QUERY", "bin/can_query"))
    parser.add_argument("--ollama", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    parser.add_argument("--model", default=os.environ.get("JARVIS_CAN_MODEL", "qwen2.5:0.5b-instruct-q4_K_M"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--show-query", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.question:
        try:
            answer_once(" ".join(args.question), args)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    print("JarvisCAN interactivo. Escribí 'salir' para terminar.")
    while True:
        try:
            question = input("vos> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in ("salir", "exit", "quit"):
            break
        try:
            answer_once(question, args)
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
