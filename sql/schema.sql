-- Esquema de JarvisCAN.
-- El binario can_logger crea esta tabla automáticamente; este archivo sirve
-- como referencia y para inspección manual.

PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;

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

CREATE INDEX IF NOT EXISTS idx_vehicle_samples_epoch
    ON vehicle_samples(epoch);
