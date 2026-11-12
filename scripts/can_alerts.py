#!/usr/bin/env python3
"""Monitores de reglas CAN con avisos por voz (Piper TTS).

Cada regla corre cada `--interval` segundos, con un desfase inicial de
`--initial-gap` segundos entre reglas para que no hablen al mismo tiempo.
Lee las ultimas muestras de SQLite y, si la condicion se cumple, genera un
WAV con voice-can.sh y lo reproduce en el audifono Bluetooth si esta presente.
"""
import argparse
import json
import math
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "vehicle.db"
DEFAULT_STATE = ROOT / "data" / "alerts_state.json"
DEFAULT_LOG = ROOT / "data" / "alerts.log"
DEFAULT_JSONL = ROOT / "data" / "alerts.jsonl"
DEFAULT_ALERT_AUDIO_DIR = ROOT / "data" / "alert_audio"
DEFAULT_VOICE = ROOT / "scripts" / "voice-can.sh"
LAST_ANSWER = ROOT / "data" / "last_answer.json"

TIRE_FIELDS = (
    ("tire_fl_kpa", "delantero izquierdo"),
    ("tire_fr_kpa", "delantero derecho"),
    ("tire_rl_kpa", "trasero izquierdo"),
    ("tire_rr_kpa", "trasero derecho"),
)
WARNING_LABELS = {
    "CHECK_ENGINE": "testigo de motor",
    "LOW_COOLANT": "nivel bajo de refrigerante",
    "LOW_OIL": "nivel bajo de aceite",
    "LOW_TIRE_PRESSURE": "presión baja de neumáticos",
    "OVERSPEED": "exceso de velocidad",
    "HIGH_COOLANT_TEMP": "temperatura alta del refrigerante",
}
SAMPLE_COLUMNS = (
    "id", "ts_utc", "epoch", "speed_kph", "coolant_c",
    "coolant_level_pct", "oil_level_pct", "tire_fl_kpa",
    "tire_fr_kpa", "tire_rl_kpa", "tire_rr_kpa",
    "dtc_codes", "warning_flags",
)
RULE_ORDER = (
    "engine_temp",
    "coolant_level",
    "tire_pressure",
    "oil_level",
    "dtc",
    "overspeed",
)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_float(value):
    if value is None or value == "":
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def fmt(value, digits=1):
    if value is None:
        return "sin dato"
    return f"{value:.{digits}f}".replace(".", ",")


def load_state(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("dtc_seen", [])
    data.setdefault("warning_seen", [])
    data.setdefault("overspeed_active", False)
    data.setdefault("last_alerts", {})
    return data


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def split_codes(text):
    if not text:
        return []
    return [part.strip() for part in str(text).split(",") if part.strip()]


def fetch_samples(conn, limit):
    available = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(vehicle_samples)").fetchall()
    }
    columns = [name for name in SAMPLE_COLUMNS if name in available]
    if "epoch" not in columns:
        return []
    order = "epoch DESC"
    if "id" in columns:
        order += ", id DESC"
    rows = conn.execute(
        f"SELECT {', '.join(columns)} FROM vehicle_samples ORDER BY {order} LIMIT ?",
        (max(1, int(limit)),),
    ).fetchall()
    return [dict(zip(columns, row)) for row in rows]


def previous_values(rows, field, samples):
    values = []
    for row in rows[1:]:
        value = as_float(row.get(field))
        if value is not None:
            values.append(value)
        if len(values) >= samples:
            break
    return values


def average(values):
    return sum(values) / len(values) if values else None


def check_engine_temp(rows, args, state):
    current = as_float(rows[0].get("coolant_c")) if rows else None
    if current is None:
        return []
    history = previous_values(rows, "coolant_c", args.samples)
    avg = average(history)
    deviation = current - avg if avg is not None else 0.0
    hot = current >= args.temp_abs
    escaped = avg is not None and len(history) >= args.min_samples and deviation >= args.temp_deviation
    if not hot and not escaped:
        return []
    detail = ""
    if avg is not None:
        detail = f" La media móvil previa era {fmt(avg)} grados."
    return [
        "Se ha detectado un valor de temperatura riesgoso, "
        f"medido en {fmt(current)} grados Celsius.{detail}"
    ]


def check_coolant_level(rows, args, state):
    current = as_float(rows[0].get("coolant_level_pct")) if rows else None
    if current is None or current > args.coolant_level:
        return []
    return [
        "Se ha detectado un nivel de refrigerante riesgoso, "
        f"medido en {fmt(current, 0)} por ciento, igual o menor al "
        f"{fmt(args.coolant_level, 0)} por ciento."
    ]


def check_tire_pressure(rows, args, state):
    if not rows:
        return []
    messages = []
    for field, label in TIRE_FIELDS:
        current = as_float(rows[0].get(field))
        if current is None:
            continue
        history = previous_values(rows, field, args.samples)
        avg = average(history)
        low = current <= args.tire_kpa
        drop = (
            avg is not None
            and len(history) >= args.min_samples
            and current <= avg * (1.0 - args.tire_drop_pct / 100.0)
        )
        if not low and not drop:
            continue
        extra = f" La media móvil previa era {fmt(avg, 0)} kilopascales." if avg is not None else ""
        messages.append(
            f"Se ha detectado una caída de presión en el neumático {label}, "
            f"medida en {fmt(current, 0)} kilopascales.{extra}"
        )
    return messages


def check_oil_level(rows, args, state):
    current = as_float(rows[0].get("oil_level_pct")) if rows else None
    if current is None or current > args.oil_level:
        return []
    return [
        "Se ha detectado un nivel de aceite riesgoso, "
        f"medido en {fmt(current, 0)} por ciento, igual o menor al "
        f"{fmt(args.oil_level, 0)} por ciento."
    ]


def check_dtc(rows, args, state):
    if not rows:
        return []
    codes = set()
    warnings = set()
    for row in rows:
        codes.update(split_codes(row.get("dtc_codes")))
        warnings.update(split_codes(row.get("warning_flags")))
    codes = sorted(codes)
    warnings = sorted(warnings)
    seen_codes = set(state.get("dtc_seen", []))
    seen_warnings = set(state.get("warning_seen", []))
    new_codes = [code for code in codes if code not in seen_codes]
    new_warnings = [warning for warning in warnings if warning not in seen_warnings]
    state["dtc_seen"] = codes
    state["warning_seen"] = warnings
    if not new_codes and not new_warnings:
        return []
    parts = []
    if new_codes:
        parts.append("códigos de falla: " + ", ".join(new_codes))
    if new_warnings:
        labels = [WARNING_LABELS.get(item, item) for item in new_warnings]
        parts.append("avisos: " + ", ".join(labels))
    return ["Se han detectado " + "; ".join(parts) + "."]


def check_overspeed(rows, args, state):
    current = as_float(rows[0].get("speed_kph")) if rows else None
    if current is None:
        return []
    if current > args.speed_limit:
        if not state.get("overspeed_active"):
            state["overspeed_active"] = True
            return [
                "Se ha detectado exceso de velocidad, "
                f"medido en {fmt(current, 0)} kilómetros por hora, "
                f"superior a {fmt(args.speed_limit, 0)}."
            ]
        return []
    state["overspeed_active"] = False
    return []


CHECKS = {
    "engine_temp": check_engine_temp,
    "coolant_level": check_coolant_level,
    "tire_pressure": check_tire_pressure,
    "oil_level": check_oil_level,
    "dtc": check_dtc,
    "overspeed": check_overspeed,
}


def log_event(args, rule, message, audio, audio_ok, played, sink, audio_file=""):
    event = {
        "ts": now_iso(),
        "epoch": int(time.time()),
        "rule": rule,
        "message": message,
        "audio_generated": bool(audio),
        "audio_ok": bool(audio_ok),
        "played_on_device": bool(played),
        "audio_sink": sink or "",
        "audio_file": audio_file or "",
    }
    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with open(args.jsonl, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    with open(args.log, "a", encoding="utf-8") as fh:
        status = "audio OK" if audio_ok else "sin audio"
        if played:
            status += f" en {sink or 'audifono'}"
        fh.write(f"{event['ts']} [{rule}] {message} ({status})\n")


def prune_alert_audio(args):
    keep = max(1, int(args.alert_audio_keep))
    try:
        files = sorted(
            args.alert_audio_dir.glob("alert_*.wav"),
            key=lambda path: path.stat().st_mtime,
        )
    except OSError:
        return
    for path in files[:-keep]:
        try:
            path.unlink()
        except OSError:
            pass


def speak(message, args, rule):
    if args.no_audio:
        return False, False, "", ""
    cmd = [
        str(args.voice_cmd),
        "--tts-test", message,
        "--play-audio", args.play_audio,
    ]
    try:
        res = subprocess.run(
            cmd, cwd=str(ROOT), text=True, capture_output=True,
            timeout=args.audio_timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"ALERTA [{message}] -> TTS agoto el tiempo", file=sys.stderr)
        return True, False, "", ""
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip().replace("\n", " ")
        print(f"ALERTA [{message}] -> TTS fallo: {detail}", file=sys.stderr)
        return True, False, "", ""
    played = False
    sink = ""
    try:
        meta = json.loads(LAST_ANSWER.read_text(encoding="utf-8"))
        played = bool(meta.get("played_on_device"))
        sink = str(meta.get("audio_sink") or "")
    except Exception:
        pass
    audio_file = ""
    wav_src = LAST_ANSWER.with_suffix(".wav")
    try:
        args.alert_audio_dir.mkdir(parents=True, exist_ok=True)
        name = f"alert_{time.time_ns()}_{rule}.wav"
        shutil.copy2(wav_src, args.alert_audio_dir / name)
        audio_file = name
        prune_alert_audio(args)
    except OSError as exc:
        print(f"ALERTA [{message}] -> no se pudo archivar el audio: {exc}", file=sys.stderr)
    return True, True, sink if played else "", audio_file


def run_rule(rule, conn, args, state):
    limit = max(args.samples + 1, 2)
    if rule == "dtc":
        limit = max(limit, args.dtc_window)
    rows = fetch_samples(conn, limit)
    if not rows:
        return 0
    messages = CHECKS[rule](rows, args, state)
    count = 0
    for message in messages:
        print(f"{now_iso()} [{rule}] {message}")
        audio = played = False
        audio_ok = True
        sink = ""
        audio_file = ""
        if args.dry_run:
            audio_ok = False
        else:
            audio, audio_ok, sink, audio_file = speak(message, args, rule)
            played = bool(sink)
            time.sleep(max(0.0, args.audio_gap))
        log_event(args, rule, message, audio, audio_ok, played, sink, audio_file)
        state.setdefault("last_alerts", {})[rule] = now_iso()
        count += 1
    return count


def parse_args():
    ap = argparse.ArgumentParser(
        description="Monitores CAN con alertas por voz.",
    )
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    ap.add_argument("--jsonl", default=str(DEFAULT_JSONL))
    ap.add_argument("--alert-audio-dir", default=str(DEFAULT_ALERT_AUDIO_DIR),
                    help="carpeta para los WAV de cada alerta (default data/alert_audio)")
    ap.add_argument("--alert-audio-keep", type=int, default=200,
                    help="cantidad maxima de WAV de alertas a conservar")
    ap.add_argument("--interval", type=float, default=180.0,
                    help="segundos entre chequeos de cada regla (default 180 = 3 min)")
    ap.add_argument("--initial-gap", type=float, default=300.0,
                    help="desfase inicial entre reglas en segundos (default 300 = 5 min)")
    ap.add_argument("--samples", type=int, default=10,
                    help="muestras previas para la media movil (default 10)")
    ap.add_argument("--min-samples", type=int, default=3,
                    help="minimo de muestras para evaluar la media movil")
    ap.add_argument("--temp-deviation", type=float, default=15.0,
                    help="salto sobre la media movil que dispara temperatura (C)")
    ap.add_argument("--temp-abs", type=float, default=105.0,
                    help="temperatura absoluta riesgosa (C)")
    ap.add_argument("--coolant-level", type=float, default=60.0,
                    help="nivel de refrigerante riesgoso (%%)")
    ap.add_argument("--oil-level", type=float, default=60.0,
                    help="nivel de aceite riesgoso (%%)")
    ap.add_argument("--tire-kpa", type=float, default=180.0,
                    help="presion absoluta baja de neumatico (kPa)")
    ap.add_argument("--tire-drop-pct", type=float, default=25.0,
                    help="caida porcentual contra la media movil")
    ap.add_argument("--speed-limit", type=float, default=130.0,
                    help="limite de velocidad (km/h)")
    ap.add_argument("--dtc-window", type=int, default=20,
                    help="muestras recientes donde buscar DTC (default 20)")
    ap.add_argument("--voice-cmd", default=str(DEFAULT_VOICE))
    ap.add_argument("--play-audio", choices=("auto", "on", "off"), default="auto")
    ap.add_argument("--audio-timeout", type=float, default=120.0)
    ap.add_argument("--audio-gap", type=float, default=1.0,
                    help="pausa entre varios audios de una misma regla")
    ap.add_argument("--no-audio", action="store_true",
                    help="no genera ni reproduce audio")
    ap.add_argument("--dry-run", action="store_true",
                    help="muestra las alertas sin generar audio")
    ap.add_argument("--once", action="store_true",
                    help="evalua todas las reglas ahora y sale")
    ap.add_argument("--only", choices=RULE_ORDER, default=None,
                    help="ejecuta solo una regla")
    ap.add_argument("--list-rules", action="store_true")
    ap.add_argument("--reset-state", action="store_true")
    return ap.parse_args()


def main():
    args = parse_args()
    if args.list_rules:
        for i, rule in enumerate(RULE_ORDER):
            print(f"{rule}\toffset={int(i * args.initial_gap)}s\tinterval={int(args.interval)}s")
        return 0
    if args.interval <= 0 or args.initial_gap < 0:
        print("--interval debe ser > 0 y --initial-gap >= 0", file=sys.stderr)
        return 2
    args.samples = max(1, args.samples)
    args.dtc_window = max(1, args.dtc_window)
    args.min_samples = max(2, args.min_samples)
    args.db = Path(args.db).expanduser().resolve()
    args.state = Path(args.state).expanduser()
    args.log = Path(args.log).expanduser()
    args.jsonl = Path(args.jsonl).expanduser()
    args.alert_audio_dir = Path(args.alert_audio_dir).expanduser().resolve()
    args.voice_cmd = Path(args.voice_cmd).expanduser()

    if not args.db.is_file():
        print(f"No existe la base: {args.db}", file=sys.stderr)
        return 3
    if not args.dry_run and not args.no_audio and not args.voice_cmd.is_file():
        print(f"No existe el comando de voz: {args.voice_cmd}", file=sys.stderr)
        return 4
    state = load_state(args.state)
    if args.reset_state:
        state = {
            "dtc_seen": [], "warning_seen": [], "overspeed_active": False,
            "last_alerts": {},
        }
        save_state(args.state, state)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rules = [args.only] if args.only else list(RULE_ORDER)

    if args.once:
        total = 0
        for rule in rules:
            total += run_rule(rule, conn, args, state)
        save_state(args.state, state)
        print(f"Chequeo unico: {total} alerta(s).")
        conn.close()
        return 0

    stop = False

    def on_signal(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    started = time.monotonic()
    next_due = {
        rule: started + i * args.initial_gap
        for i, rule in enumerate(rules)
    }
    print(f"Monitores activos: {', '.join(rules)}")
    print(
        f"Intervalo {args.interval:.0f}s, desfase inicial {args.initial_gap:.0f}s, "
        f"DB {args.db}"
    )
    for rule in rules:
        offset = int(next_due[rule] - started)
        print(f"  {rule}: primer chequeo en {offset}s")
    while not stop:
        current = time.monotonic()
        for rule in rules:
            if current < next_due[rule]:
                continue
            try:
                run_rule(rule, conn, args, state)
            except Exception as exc:
                print(f"{now_iso()} [{rule}] error: {exc}", file=sys.stderr)
            save_state(args.state, state)
            next_due[rule] += args.interval
            if next_due[rule] <= current:
                next_due[rule] = current + args.interval
        pending = [next_due[rule] - time.monotonic() for rule in rules]
        wait = min(pending) if pending else 1.0
        deadline = time.monotonic() + max(0.2, min(wait, 5.0))
        while not stop and time.monotonic() < deadline:
            time.sleep(0.2)
    conn.close()
    save_state(args.state, state)
    print("Monitores detenidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
