#define _GNU_SOURCE
#include "db.h"

#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

static int mkdir_p(const char *path)
{
    char tmp[PATH_MAX];
    size_t len;
    if (!path || !*path) {
        return 0;
    }
    len = strlen(path);
    if (len >= sizeof(tmp)) {
        errno = ENAMETOOLONG;
        return -1;
    }
    memcpy(tmp, path, len + 1);
    while (len > 1 && tmp[len - 1] == '/') {
        tmp[--len] = '\0';
    }
    for (char *p = tmp + 1; *p; p++) {
        if (*p != '/') {
            continue;
        }
        *p = '\0';
        if (mkdir(tmp, 0755) != 0 && errno != EEXIST) {
            return -1;
        }
        *p = '/';
    }
    if (mkdir(tmp, 0755) != 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

int db_ensure_parent(const char *path)
{
    char tmp[PATH_MAX];
    char *slash;
    if (!path || !*path) {
        return 0;
    }
    if (strlen(path) >= sizeof(tmp)) {
        errno = ENAMETOOLONG;
        return -1;
    }
    memcpy(tmp, path, strlen(path) + 1);
    slash = strrchr(tmp, '/');
    if (!slash || slash == tmp) {
        return 0;
    }
    *slash = '\0';
    return mkdir_p(tmp);
}

static int exec_sql(sqlite3 *db, const char *sql)
{
    char *err = NULL;
    int rc = sqlite3_exec(db, sql, NULL, NULL, &err);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "sqlite: %s\n", err ? err : sqlite3_errmsg(db));
        sqlite3_free(err);
        return -1;
    }
    return 0;
}

int db_open(const char *path, sqlite3 **out)
{
    sqlite3 *db = NULL;
    int rc;
    if (!path || !out) {
        return -1;
    }
    if (db_ensure_parent(path) != 0) {
        fprintf(stderr, "no se pudo crear el directorio de %s: %s\n", path, strerror(errno));
        return -1;
    }
    rc = sqlite3_open_v2(path, &db,
                         SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX,
                         NULL);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "no se pudo abrir %s: %s\n", path, db ? sqlite3_errmsg(db) : "sin detalle");
        if (db) {
            sqlite3_close(db);
        }
        return -1;
    }
    sqlite3_busy_timeout(db, 5000);
    if (exec_sql(db, "PRAGMA journal_mode=WAL;") != 0 ||
        exec_sql(db, "PRAGMA synchronous=NORMAL;") != 0 ||
        exec_sql(db, "PRAGMA temp_store=MEMORY;") != 0) {
        sqlite3_close(db);
        return -1;
    }
    *out = db;
    return 0;
}

void db_close(sqlite3 *db)
{
    if (db) {
        sqlite3_close(db);
    }
}

int db_init(sqlite3 *db)
{
    const char *sql =
        "CREATE TABLE IF NOT EXISTS vehicle_samples ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " ts_utc TEXT NOT NULL,"
        " epoch INTEGER NOT NULL,"
        " source TEXT NOT NULL,"
        " pid_count INTEGER NOT NULL DEFAULT 0,"
        " speed_kph REAL,"
        " rpm REAL,"
        " coolant_c REAL,"
        " engine_load_pct REAL,"
        " throttle_pct REAL,"
        " fuel_level_pct REAL,"
        " intake_air_c REAL,"
        " maf_gps REAL,"
        " fuel_pressure_kpa REAL,"
        " map_kpa REAL,"
        " timing_advance_deg REAL,"
        " run_time_s REAL,"
        " battery_v REAL,"
        " oil_temp_c REAL,"
        " barometric_kpa REAL,"
        " short_fuel_trim_pct REAL,"
        " long_fuel_trim_pct REAL,"
        " catalyst_temp_c REAL,"
        " ambient_air_c REAL,"
        " coolant_level_pct REAL,"
        " oil_level_pct REAL,"
        " tire_fl_kpa REAL,"
        " tire_fr_kpa REAL,"
        " tire_rl_kpa REAL,"
        " tire_rr_kpa REAL,"
        " dtc_codes TEXT,"
        " warning_flags TEXT,"
        " raw_json TEXT NOT NULL DEFAULT '{}'"
        ");"
        "CREATE INDEX IF NOT EXISTS idx_vehicle_samples_epoch ON vehicle_samples(epoch);";
    static const struct {
        const char *name;
        const char *decl;
    } extra[] = {
        {"coolant_level_pct", "REAL"},
        {"oil_level_pct", "REAL"},
        {"tire_fl_kpa", "REAL"},
        {"tire_fr_kpa", "REAL"},
        {"tire_rl_kpa", "REAL"},
        {"tire_rr_kpa", "REAL"},
        {"dtc_codes", "TEXT"},
        {"warning_flags", "TEXT"},
        {NULL, NULL}
    };
    sqlite3_stmt *stmt = NULL;
    int rc;

    if (exec_sql(db, sql) != 0) {
        return -1;
    }
    for (int i = 0; extra[i].name; i++) {
        int exists = 0;
        rc = sqlite3_prepare_v2(db, "PRAGMA table_info(vehicle_samples);", -1, &stmt, NULL);
        if (rc != SQLITE_OK) {
            return -1;
        }
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char *name = sqlite3_column_text(stmt, 1);
            if (name && strcmp((const char *)name, extra[i].name) == 0) {
                exists = 1;
                break;
            }
        }
        sqlite3_finalize(stmt);
        stmt = NULL;
        if (!exists) {
            char alter[256];
            snprintf(alter, sizeof(alter),
                     "ALTER TABLE vehicle_samples ADD COLUMN %s %s;",
                     extra[i].name, extra[i].decl);
            if (exec_sql(db, alter) != 0) {
                return -1;
            }
        }
    }
    return 0;
}

static void bind_optional_double(sqlite3_stmt *stmt, int index, double value)
{
    if (isnan(value)) {
        sqlite3_bind_null(stmt, index);
    } else {
        sqlite3_bind_double(stmt, index, value);
    }
}

int db_insert(sqlite3 *db, const VehicleSample *s)
{
    static const char *sql =
        "INSERT INTO vehicle_samples ("
        " ts_utc, epoch, source, pid_count,"
        " speed_kph, rpm, coolant_c, engine_load_pct, throttle_pct, fuel_level_pct,"
        " intake_air_c, maf_gps, fuel_pressure_kpa, map_kpa, timing_advance_deg,"
        " run_time_s, battery_v, oil_temp_c, barometric_kpa,"
        " short_fuel_trim_pct, long_fuel_trim_pct, catalyst_temp_c, ambient_air_c,"
        " coolant_level_pct, oil_level_pct, tire_fl_kpa, tire_fr_kpa,"
        " tire_rl_kpa, tire_rr_kpa, dtc_codes, warning_flags, raw_json"
        ") VALUES ("
        " ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15,"
        " ?16, ?17, ?18, ?19, ?20, ?21, ?22, ?23, ?24, ?25, ?26, ?27, ?28,"
        " ?29, ?30, ?31, ?32"
        ");";
    sqlite3_stmt *stmt = NULL;
    int rc;

    rc = sqlite3_prepare_v2(db, sql, -1, &stmt, NULL);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "sqlite prepare: %s\n", sqlite3_errmsg(db));
        return -1;
    }
    sqlite3_bind_text(stmt, 1, s->ts_utc, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, s->epoch);
    sqlite3_bind_text(stmt, 3, s->source, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 4, s->pid_count);
    bind_optional_double(stmt, 5, s->speed_kph);
    bind_optional_double(stmt, 6, s->rpm);
    bind_optional_double(stmt, 7, s->coolant_c);
    bind_optional_double(stmt, 8, s->engine_load_pct);
    bind_optional_double(stmt, 9, s->throttle_pct);
    bind_optional_double(stmt, 10, s->fuel_level_pct);
    bind_optional_double(stmt, 11, s->intake_air_c);
    bind_optional_double(stmt, 12, s->maf_gps);
    bind_optional_double(stmt, 13, s->fuel_pressure_kpa);
    bind_optional_double(stmt, 14, s->map_kpa);
    bind_optional_double(stmt, 15, s->timing_advance_deg);
    bind_optional_double(stmt, 16, s->run_time_s);
    bind_optional_double(stmt, 17, s->battery_v);
    bind_optional_double(stmt, 18, s->oil_temp_c);
    bind_optional_double(stmt, 19, s->barometric_kpa);
    bind_optional_double(stmt, 20, s->short_fuel_trim_pct);
    bind_optional_double(stmt, 21, s->long_fuel_trim_pct);
    bind_optional_double(stmt, 22, s->catalyst_temp_c);
    bind_optional_double(stmt, 23, s->ambient_air_c);
    bind_optional_double(stmt, 24, s->coolant_level_pct);
    bind_optional_double(stmt, 25, s->oil_level_pct);
    bind_optional_double(stmt, 26, s->tire_fl_kpa);
    bind_optional_double(stmt, 27, s->tire_fr_kpa);
    bind_optional_double(stmt, 28, s->tire_rl_kpa);
    bind_optional_double(stmt, 29, s->tire_rr_kpa);
    if (s->dtc_codes[0]) {
        sqlite3_bind_text(stmt, 30, s->dtc_codes, -1, SQLITE_TRANSIENT);
    } else {
        sqlite3_bind_null(stmt, 30);
    }
    if (s->warning_flags[0]) {
        sqlite3_bind_text(stmt, 31, s->warning_flags, -1, SQLITE_TRANSIENT);
    } else {
        sqlite3_bind_null(stmt, 31);
    }
    sqlite3_bind_text(stmt, 32, s->raw_json, -1, SQLITE_TRANSIENT);

    rc = sqlite3_step(stmt);
    if (rc != SQLITE_DONE) {
        fprintf(stderr, "sqlite insert: %s\n", sqlite3_errmsg(db));
        sqlite3_finalize(stmt);
        return -1;
    }
    sqlite3_finalize(stmt);
    return 0;
}
