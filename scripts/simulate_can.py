#!/usr/bin/env python3
"""Genera tramas OBD-II ficticias y las inserta en la base de JarvisCAN.

No necesita hardware CAN: simula una ECU, codifica las respuestas como tramas
OBD-II, las decodifica y guarda una muestra por intervalo en SQLite.
"""
import argparse
import json
import math
import random
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "vehicle.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicle_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    source TEXT NOT NULL,
    pid_count INTEGER NOT NULL DEFAULT 0,
    speed_kph REAL,
    rpm REAL,
    coolant_c REAL,
    engine_load_pct REAL,
    throttle_pct REAL,
    fuel_level_pct REAL,
    intake_air_c REAL,
    maf_gps REAL,
    fuel_pressure_kpa REAL,
    map_kpa REAL,
    timing_advance_deg REAL,
    run_time_s REAL,
    battery_v REAL,
    oil_temp_c REAL,
    barometric_kpa REAL,
    short_fuel_trim_pct REAL,
    long_fuel_trim_pct REAL,
    catalyst_temp_c REAL,
    ambient_air_c REAL,
    coolant_level_pct REAL,
    oil_level_pct REAL,
    tire_fl_kpa REAL,
    tire_fr_kpa REAL,
    tire_rl_kpa REAL,
    tire_rr_kpa REAL,
    dtc_codes TEXT,
    warning_flags TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_vehicle_samples_epoch ON vehicle_samples(epoch);
"""
COLUMNS = [
    "ts_utc", "epoch", "source", "pid_count",
    "speed_kph", "rpm", "coolant_c", "engine_load_pct", "throttle_pct",
    "fuel_level_pct", "intake_air_c", "maf_gps", "fuel_pressure_kpa",
    "map_kpa", "timing_advance_deg", "run_time_s", "battery_v",
    "oil_temp_c", "barometric_kpa", "short_fuel_trim_pct",
    "long_fuel_trim_pct", "catalyst_temp_c", "ambient_air_c",
    "coolant_level_pct", "oil_level_pct",
    "tire_fl_kpa", "tire_fr_kpa", "tire_rl_kpa", "tire_rr_kpa",
    "dtc_codes", "warning_flags", "raw_json",
]
PIDS = [
    0x04, 0x05, 0x06, 0x07, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    0x10, 0x11, 0x1F, 0x2F, 0x33, 0x3C, 0x42, 0x46, 0x5C,
]
METRIC_FIELDS = [
    "speed_kph", "rpm", "coolant_c", "engine_load_pct", "throttle_pct",
    "fuel_level_pct", "intake_air_c", "maf_gps", "fuel_pressure_kpa",
    "map_kpa", "timing_advance_deg", "run_time_s", "battery_v",
    "oil_temp_c", "barometric_kpa", "short_fuel_trim_pct",
    "long_fuel_trim_pct", "catalyst_temp_c", "ambient_air_c",
    "coolant_level_pct", "oil_level_pct",
    "tire_fl_kpa", "tire_fr_kpa", "tire_rl_kpa", "tire_rr_kpa",
]
RESUME_MAP = {
    "speed_kph": "speed",
    "rpm": "rpm",
    "coolant_c": "coolant",
    "engine_load_pct": "load",
    "throttle_pct": "throttle",
    "fuel_level_pct": "fuel",
    "intake_air_c": "intake",
    "maf_gps": "maf",
    "fuel_pressure_kpa": "fuel_pressure",
    "map_kpa": "map",
    "timing_advance_deg": "timing",
    "run_time_s": "run_time",
    "battery_v": "battery",
    "oil_temp_c": "oil",
    "barometric_kpa": "barometric",
    "short_fuel_trim_pct": "stft",
    "long_fuel_trim_pct": "ltft",
    "catalyst_temp_c": "catalyst",
    "ambient_air_c": "ambient",
    "coolant_level_pct": "coolant_level",
    "oil_level_pct": "oil_level",
    "tire_fl_kpa": "tire_fl",
    "tire_fr_kpa": "tire_fr",
    "tire_rl_kpa": "tire_rl",
    "tire_rr_kpa": "tire_rr",
}

TIRE_FIELDS = ("tire_fl_kpa", "tire_fr_kpa", "tire_rl_kpa", "tire_rr_kpa")
TIRE_BASE = (235.0, 236.0, 233.0, 234.0)
TIRE_LABELS = {
    "tire_fl_kpa": "delantero izquierdo",
    "tire_fr_kpa": "delantero derecho",
    "tire_rl_kpa": "trasero izquierdo",
    "tire_rr_kpa": "trasero derecho",
}
DTC_POOL = (
    "P0128", "P0300", "P0171", "P0420", "C0035", "U0100",
)
WARNING_BITS = {
    "CHECK_ENGINE": 1,
    "LOW_COOLANT": 2,
    "LOW_OIL": 4,
    "LOW_TIRE_PRESSURE": 8,
    "OVERSPEED": 16,
    "HIGH_COOLANT_TEMP": 32,
}
ANOMALY_TYPES = (
    "engine_temp", "coolant_level", "tire_pressure",
    "oil_level", "dtc", "overspeed",
)
ANOMALY_HOLD = 5
CUSTOM_FRAME_TIRE = 0x600
CUSTOM_FRAME_LEVELS = 0x601
CUSTOM_FRAME_DTC = 0x602
CUSTOM_FRAME_WARNINGS = 0x603


def ensure_columns(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(vehicle_samples)")}
    additions = {
        "coolant_level_pct": "REAL",
        "oil_level_pct": "REAL",
        "tire_fl_kpa": "REAL",
        "tire_fr_kpa": "REAL",
        "tire_rl_kpa": "REAL",
        "tire_rr_kpa": "REAL",
        "dtc_codes": "TEXT",
        "warning_flags": "TEXT",
    }
    for name, decl in additions.items():
        if name not in existing:
            conn.execute("ALTER TABLE vehicle_samples ADD COLUMN %s %s" % (name, decl))


def clamp(value, low, high):
    return max(low, min(high, value))


def put_u16(value):
    raw = int(clamp(value, 0, 65535))
    return bytes([(raw >> 8) & 0xFF, raw & 0xFF])


class FakeEcu:
    """ECU OBD-II simulada con un ciclo de conducción de 300 s."""

    def __init__(self, seed=42, ambient=24.0, fuel=72.0,
                 anomaly="random", anomaly_every=7, dtc_every=0):
        self.rng = random.Random(seed)
        self.anomaly_mode = anomaly
        self.anomaly_every = max(0, int(anomaly_every))
        self.dtc_every = max(0, int(dtc_every))
        self.sample_index = 0
        self.anomaly = None
        self.anomaly_left = 0
        self.anomaly_tire = TIRE_FIELDS[0]
        self.anomaly_dtcs = []
        self.t = 0.0
        self.speed = 0.0
        self.rpm = 780.0
        self.coolant = 22.0
        self.load = 18.0
        self.throttle = 4.0
        self.fuel = fuel
        self.intake = ambient
        self.maf = 3.0
        self.fuel_pressure = 310.0
        self.map = 32.0
        self.timing = 12.0
        self.battery = 12.4
        self.oil = 24.0
        self.barometric = 101.3
        self.stft = 0.0
        self.ltft = 0.0
        self.catalyst = 25.0
        self.ambient = ambient
        self.run_time = 0.0
        self.coolant_level = 88.0
        self.oil_level = 84.0
        self.tire_fl = TIRE_BASE[0]
        self.tire_fr = TIRE_BASE[1]
        self.tire_rl = TIRE_BASE[2]
        self.tire_rr = TIRE_BASE[3]
        self.dtcs = []
        self.warnings = []

    def advance(self, dt):
        if dt <= 0:
            return
        steps = max(1, int(math.ceil(dt)))
        sub = dt / steps
        for _ in range(steps):
            self._step(sub)

    def _step(self, dt):
        self.t += dt
        self.run_time += dt
        cycle = self.t % 300.0
        if cycle < 30.0:
            target_speed, target_throttle = 0.0, 4.0
        elif cycle < 90.0:
            target_speed, target_throttle = 75.0, 38.0
        elif cycle < 180.0:
            target_speed, target_throttle = 85.0, 18.0
        elif cycle < 220.0:
            target_speed, target_throttle = 30.0, 4.0
        elif cycle < 260.0:
            target_speed, target_throttle = 0.0, 4.0
        else:
            target_speed, target_throttle = 60.0, 30.0

        self.speed += (target_speed - self.speed) * (1.0 - math.exp(-dt / 8.0))
        self.throttle += (target_throttle - self.throttle) * (1.0 - math.exp(-dt / 3.0))
        self.load += ((15.0 + self.throttle * 0.85) - self.load) * (1.0 - math.exp(-dt / 2.0))
        target_rpm = 760.0 + self.speed * 26.0 + self.throttle * 10.0
        if self.speed < 1.0:
            target_rpm += 25.0 * math.sin(self.t * 2.0)
        self.rpm += (target_rpm - self.rpm) * (1.0 - math.exp(-dt / 1.5))
        self.coolant += (92.0 - self.coolant) * (1.0 - math.exp(-dt / 180.0))
        self.oil += ((self.coolant + 8.0) - self.oil) * (1.0 - math.exp(-dt / 150.0))
        self.intake += ((self.ambient + 5.0 + self.load * 0.08) - self.intake) * (1.0 - math.exp(-dt / 8.0))
        self.maf += ((1.5 + self.rpm * self.load / 8000.0) - self.maf) * (1.0 - math.exp(-dt / 2.0))
        self.fuel_pressure += ((300.0 + self.load * 1.2) - self.fuel_pressure) * (1.0 - math.exp(-dt / 2.0))
        self.map += ((25.0 + self.load * 0.75) - self.map) * (1.0 - math.exp(-dt / 2.0))
        self.timing += ((12.0 + (100.0 - self.load) * 0.18 + self.speed * 0.04) - self.timing) * (1.0 - math.exp(-dt / 2.0))
        self.battery += (((14.1 if self.rpm > 800.0 else 12.3) + 0.15 * math.sin(self.t * 1.7)) - self.battery) * (1.0 - math.exp(-dt / 2.0))
        self.fuel = clamp(self.fuel - dt * 0.0005, 0.0, 100.0)
        self.stft = 2.0 * math.sin(self.t * 0.30)
        self.ltft = -1.0 + 0.5 * math.sin(self.t * 0.05)
        self.catalyst += (((250.0 if self.coolant < 60.0 else 620.0)) - self.catalyst) * (1.0 - math.exp(-dt / 60.0))
        self.ambient = 24.0 + 1.5 * math.sin(self.t * 0.01)
        self.barometric = 101.3 + 0.4 * math.sin(self.t * 0.03)
        self.coolant_level = clamp(self.coolant_level - dt * 0.0004, 0.0, 100.0)
        self.oil_level = clamp(self.oil_level - dt * 0.0002, 0.0, 100.0)
        if self.anomaly_left <= 0:
            for name, base in zip(TIRE_FIELDS, TIRE_BASE):
                value = getattr(self, RESUME_MAP[name])
                target = base + 2.0 * math.sin(self.t * 0.01 + base)
                setattr(self, RESUME_MAP[name], value + (target - value) * (1.0 - math.exp(-dt / 20.0)))

        # Ruido pequeño, como el de una lectura real.
        self.speed = clamp(self.speed + self.rng.uniform(-0.15, 0.15), 0.0, 130.0)
        self.rpm = clamp(self.rpm + self.rng.uniform(-8.0, 8.0), 650.0, 4500.0)
        self.coolant = clamp(self.coolant + self.rng.uniform(-0.1, 0.1), 20.0, 105.0)
        self.oil = clamp(self.oil + self.rng.uniform(-0.1, 0.1), 20.0, 120.0)

    def read_pid(self, pid):
        """Devuelve la carga útil OBD-II (bytes A, B, ...) para un PID."""
        if pid == 0x04:
            return bytes([int(clamp(self.load * 255.0 / 100.0, 0, 255))])
        if pid == 0x05:
            return bytes([int(clamp(self.coolant + 40.0, 0, 255))])
        if pid == 0x06:
            return bytes([int(clamp((self.stft + 100.0) * 1.28, 0, 255))])
        if pid == 0x07:
            return bytes([int(clamp((self.ltft + 100.0) * 1.28, 0, 255))])
        if pid == 0x0A:
            return bytes([int(clamp(self.fuel_pressure / 3.0, 0, 255))])
        if pid == 0x0B:
            return bytes([int(clamp(self.map, 0, 255))])
        if pid == 0x0C:
            return put_u16(self.rpm * 4.0)
        if pid == 0x0D:
            return bytes([int(clamp(self.speed, 0, 255))])
        if pid == 0x0E:
            return bytes([int(clamp((self.timing + 64.0) * 2.0, 0, 255))])
        if pid == 0x0F:
            return bytes([int(clamp(self.intake + 40.0, 0, 255))])
        if pid == 0x10:
            return put_u16(self.maf * 100.0)
        if pid == 0x11:
            return bytes([int(clamp(self.throttle * 255.0 / 100.0, 0, 255))])
        if pid == 0x1F:
            return put_u16(self.run_time)
        if pid == 0x2F:
            return bytes([int(clamp(self.fuel * 255.0 / 100.0, 0, 255))])
        if pid == 0x33:
            return bytes([int(clamp(self.barometric, 0, 255))])
        if pid == 0x3C:
            return put_u16((self.catalyst + 40.0) * 10.0)
        if pid == 0x42:
            return put_u16(self.battery * 1000.0)
        if pid == 0x46:
            return bytes([int(clamp(self.ambient + 40.0, 0, 255))])
        if pid == 0x5C:
            return bytes([int(clamp(self.oil + 40.0, 0, 255))])
        raise ValueError("PID no soportado: 0x%02X" % pid)

    def resume_from(self, row):
        """Continúa desde la última muestra para no dar saltos irreales."""
        for field, value in zip(METRIC_FIELDS, row):
            if value is not None:
                setattr(self, RESUME_MAP[field], float(value))
        self.t = float(self.run_time) % 300.0

    def _pick_anomaly(self):
        if self.anomaly_mode == "none":
            return None
        if self.anomaly_mode == "all":
            return "all"
        if self.anomaly_mode != "random":
            return self.anomaly_mode
        return self.rng.choice(ANOMALY_TYPES)

    def _apply_anomaly(self):
        kind = self.anomaly
        if kind in ("engine_temp", "all"):
            self.coolant = 118.0
            self.oil = 112.0
            if "HIGH_COOLANT_TEMP" not in self.warnings:
                self.warnings.append("HIGH_COOLANT_TEMP")
        if kind in ("coolant_level", "all"):
            self.coolant_level = 52.0
            if "LOW_COOLANT" not in self.warnings:
                self.warnings.append("LOW_COOLANT")
        if kind in ("tire_pressure", "all"):
            field = self.anomaly_tire
            setattr(self, RESUME_MAP[field], 162.0)
            if "LOW_TIRE_PRESSURE" not in self.warnings:
                self.warnings.append("LOW_TIRE_PRESSURE")
        if kind in ("oil_level", "all"):
            self.oil_level = 48.0
            if "LOW_OIL" not in self.warnings:
                self.warnings.append("LOW_OIL")
        if kind in ("dtc", "all"):
            self.dtcs = list(self.anomaly_dtcs)
            if "CHECK_ENGINE" not in self.warnings:
                self.warnings.append("CHECK_ENGINE")
        if kind in ("overspeed", "all"):
            self.speed = 146.0
            self.rpm = 3900.0
            self.throttle = 65.0
            if "OVERSPEED" not in self.warnings:
                self.warnings.append("OVERSPEED")

    def _clear_anomaly(self):
        self.coolant = 92.0
        self.oil = 100.0
        self.coolant_level = 88.0
        self.oil_level = 84.0
        self.tire_fl, self.tire_fr, self.tire_rl, self.tire_rr = TIRE_BASE
        self.speed = 80.0
        self.rpm = 2600.0
        self.throttle = 22.0
        self.dtcs = []
        self.warnings = []
        self.anomaly = None

    def _maybe_anomaly(self):
        self.sample_index += 1
        if self.anomaly_left > 0:
            self._apply_anomaly()
            self.anomaly_left -= 1
            return
        forced_dtc = (
            self.dtc_every > 0
            and self.sample_index % self.dtc_every == 0
        )
        if forced_dtc:
            self.anomaly = "dtc"
        else:
            if self.anomaly_every <= 0 or self.anomaly_mode == "none":
                return
            if self.sample_index % self.anomaly_every != 0:
                return
            self.anomaly = self._pick_anomaly()
        if self.anomaly:
            self.anomaly_tire = self.rng.choice(TIRE_FIELDS)
            self.anomaly_dtcs = self.rng.sample(DTC_POOL, 2)
            self._apply_anomaly()
            self.anomaly_left = ANOMALY_HOLD - 1

    def custom_frames(self):
        tire_data = bytes(
            int(clamp(getattr(self, RESUME_MAP[name]) / 2.0, 0, 255))
            for name in TIRE_FIELDS
        )
        levels = bytes([
            int(clamp(self.coolant_level, 0, 100)),
            int(clamp(self.oil_level, 0, 100)),
        ])
        frames = [
            (CUSTOM_FRAME_TIRE, tire_data),
            (CUSTOM_FRAME_LEVELS, levels),
        ]
        for code in self.dtcs[:2]:
            raw = code.encode("ascii")[:7]
            frames.append((CUSTOM_FRAME_DTC, bytes([len(raw)]) + raw))
        mask = 0
        for warning in self.warnings:
            mask |= WARNING_BITS.get(warning, 0)
        frames.append((CUSTOM_FRAME_WARNINGS, bytes([mask & 0xFF])))
        return frames

    def sample(self):
        """Pide todos los PIDs, decodifica y devuelve una muestra."""
        self._maybe_anomaly()
        data = {pid: self.read_pid(pid) for pid in PIDS}
        result = {
            "speed_kph": data[0x0D][0],
            "rpm": (data[0x0C][0] * 256 + data[0x0C][1]) / 4.0,
            "coolant_c": data[0x05][0] - 40.0,
            "engine_load_pct": data[0x04][0] * 100.0 / 255.0,
            "throttle_pct": data[0x11][0] * 100.0 / 255.0,
            "fuel_level_pct": data[0x2F][0] * 100.0 / 255.0,
            "intake_air_c": data[0x0F][0] - 40.0,
            "maf_gps": (data[0x10][0] * 256 + data[0x10][1]) / 100.0,
            "fuel_pressure_kpa": data[0x0A][0] * 3.0,
            "map_kpa": data[0x0B][0],
            "timing_advance_deg": data[0x0E][0] / 2.0 - 64.0,
            "run_time_s": data[0x1F][0] * 256 + data[0x1F][1],
            "battery_v": (data[0x42][0] * 256 + data[0x42][1]) / 1000.0,
            "oil_temp_c": data[0x5C][0] - 40.0,
            "barometric_kpa": data[0x33][0],
            "short_fuel_trim_pct": data[0x06][0] / 1.28 - 100.0,
            "long_fuel_trim_pct": data[0x07][0] / 1.28 - 100.0,
            "catalyst_temp_c": (data[0x3C][0] * 256 + data[0x3C][1]) / 10.0 - 40.0,
            "ambient_air_c": data[0x46][0] - 40.0,
            "coolant_level_pct": self.coolant_level,
            "oil_level_pct": self.oil_level,
            "tire_fl_kpa": self.tire_fl,
            "tire_fr_kpa": self.tire_fr,
            "tire_rl_kpa": self.tire_rl,
            "tire_rr_kpa": self.tire_rr,
            "dtc_codes": ",".join(self.dtcs),
            "warning_flags": ",".join(self.warnings),
            "custom_frame_count": len(self.custom_frames()),
            "custom_frames": [
                {"id": "0x%03X" % cid, "data": data.hex()}
                for cid, data in self.custom_frames()
            ],
        }
        if self.anomaly is not None and self.anomaly_left == 0:
            self._clear_anomaly()
        return result


def connect(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    ensure_columns(conn)
    return conn


def insert_sample(conn, epoch, values, source="can_sim"):
    ts_utc = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = dict(values)
    frame_count = len(PIDS) + int(values.get("custom_frame_count", 0))
    raw.update({"source": source, "pid_count": frame_count, "simulated": True})
    row = {
        "ts_utc": ts_utc,
        "epoch": int(epoch),
        "source": source,
        "pid_count": frame_count,
        **values,
        "raw_json": json.dumps(raw, separators=(",", ":")),
    }
    sql = "INSERT INTO vehicle_samples (%s) VALUES (%s)" % (
        ", ".join(COLUMNS), ", ".join("?" for _ in COLUMNS)
    )
    conn.execute(sql, [row[col] for col in COLUMNS])


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inserta datos CAN/OBD-II ficticios en la base de JarvisCAN."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="base SQLite")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="segundos entre muestras en modo continuo")
    parser.add_argument("--count", type=int, default=1,
                        help="cantidad de muestras; 0 = continuo")
    parser.add_argument("--history-minutes", type=float, default=0.0,
                        help="genera muestras de las últimas N minutos")
    parser.add_argument("--step", type=float, default=60.0,
                        help="segundos entre muestras históricas")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true",
                        help="borra vehicle_samples antes de insertar")
    parser.add_argument("--no-resume", action="store_true",
                        help="no continúa desde la última muestra de la base")
    parser.add_argument("--anomaly", default="random",
                        choices=("random", "none", "all", "engine_temp",
                                 "coolant_level", "tire_pressure", "oil_level",
                                 "dtc", "overspeed"),
                        help="tipo de anomalía inyectada (default: random)")
    parser.add_argument("--anomaly-every", type=int, default=7,
                        help="cada N muestras inyecta una anomalía; 0 la desactiva")
    parser.add_argument("--dtc-every", type=int, default=0,
                        help="fuerza un DTC cada N muestras; 0 lo desactiva")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.interval <= 0 or args.step <= 0:
        print("interval y step deben ser mayores que cero", file=sys.stderr)
        return 2
    if args.count < 0:
        print("count no puede ser negativo", file=sys.stderr)
        return 2

    db_path = Path(args.db).expanduser().resolve()
    conn = connect(db_path)
    if args.reset:
        conn.execute("DELETE FROM vehicle_samples")
        conn.commit()

    ecu = FakeEcu(seed=args.seed, anomaly=args.anomaly,
                  anomaly_every=args.anomaly_every,
                  dtc_every=args.dtc_every)
    now = time.time()
    if not args.reset and not args.no_resume and args.history_minutes <= 0:
        try:
            row = conn.execute(
                "SELECT epoch, %s FROM vehicle_samples ORDER BY epoch DESC, id DESC LIMIT 1"
                % ", ".join(METRIC_FIELDS)
            ).fetchone()
        except sqlite3.Error:
            row = None
        if row:
            last_epoch, values = row[0], row[1:]
            ecu.resume_from(values)
            ecu.advance(max(0.0, min(now - float(last_epoch), 300.0)))
    inserted = 0
    stop = False

    def on_signal(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        if args.history_minutes > 0:
            total = max(1, int(round(args.history_minutes * 60.0 / args.step)) + 1)
            start = now - (total - 1) * args.step
            for i in range(total):
                if i:
                    ecu.advance(args.step)
                insert_sample(conn, start + i * args.step, ecu.sample())
                inserted += 1
                if not args.quiet and (inserted == 1 or inserted % 20 == 0 or inserted == total):
                    print("insertadas %d/%d" % (inserted, total), file=sys.stderr)
            conn.commit()
        elif args.count == 0:
            while not stop:
                insert_sample(conn, time.time(), ecu.sample())
                conn.commit()
                inserted += 1
                if not args.quiet:
                    print("muestra %d insertada" % inserted, file=sys.stderr)
                deadline = time.time() + args.interval
                while not stop and time.time() < deadline:
                    time.sleep(min(0.5, max(0.0, deadline - time.time())))
                if not stop:
                    ecu.advance(args.interval)
        else:
            for i in range(args.count):
                insert_sample(conn, time.time(), ecu.sample())
                conn.commit()
                inserted += 1
                if i + 1 < args.count:
                    time.sleep(args.interval)
                    ecu.advance(args.interval)
                    # El tiempo real transcurrido ya avanzó la ECU; el ciclo
                    # interno se mantiene coherente con el intervalo pedido.
    finally:
        conn.close()

    if not args.quiet:
        print("OK: %d muestra(s) en %s" % (inserted, db_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
