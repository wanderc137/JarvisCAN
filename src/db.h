#ifndef JARVIS_CAN_DB_H
#define JARVIS_CAN_DB_H

#include <stdint.h>
#include <sqlite3.h>

typedef struct {
    int64_t epoch;
    char ts_utc[32];
    char source[24];
    int pid_count;
    double speed_kph;
    double rpm;
    double coolant_c;
    double engine_load_pct;
    double throttle_pct;
    double fuel_level_pct;
    double intake_air_c;
    double maf_gps;
    double fuel_pressure_kpa;
    double map_kpa;
    double timing_advance_deg;
    double run_time_s;
    double battery_v;
    double oil_temp_c;
    double barometric_kpa;
    double short_fuel_trim_pct;
    double long_fuel_trim_pct;
    double catalyst_temp_c;
    double ambient_air_c;
    double coolant_level_pct;
    double oil_level_pct;
    double tire_fl_kpa;
    double tire_fr_kpa;
    double tire_rl_kpa;
    double tire_rr_kpa;
    char dtc_codes[160];
    char warning_flags[160];
    char raw_json[2048];
} VehicleSample;

int db_open(const char *path, sqlite3 **out);
void db_close(sqlite3 *db);
int db_init(sqlite3 *db);
int db_insert(sqlite3 *db, const VehicleSample *sample);
int db_ensure_parent(const char *path);

#endif
