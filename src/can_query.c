#define _GNU_SOURCE
#include <getopt.h>
#include <inttypes.h>
#include <math.h>
#include <sqlite3.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    const char *name;
    const char *label;
    const char *unit;
} Metric;

static const Metric METRICS[] = {
    {"speed_kph", "Velocidad", "km/h"},
    {"rpm", "RPM", "rpm"},
    {"coolant_c", "Temp. refrigerante", "C"},
    {"engine_load_pct", "Carga motor", "%"},
    {"throttle_pct", "Acelerador", "%"},
    {"fuel_level_pct", "Nivel combustible", "%"},
    {"intake_air_c", "Temp. aire admision", "C"},
    {"maf_gps", "MAF", "g/s"},
    {"fuel_pressure_kpa", "Presion combustible", "kPa"},
    {"map_kpa", "MAP", "kPa"},
    {"timing_advance_deg", "Avance encendido", "grados"},
    {"run_time_s", "Tiempo motor", "s"},
    {"battery_v", "Voltaje bateria", "V"},
    {"oil_temp_c", "Temp. aceite", "C"},
    {"barometric_kpa", "Presion barometrica", "kPa"},
    {"short_fuel_trim_pct", "STFT", "%"},
    {"long_fuel_trim_pct", "LTFT", "%"},
    {"catalyst_temp_c", "Temp. catalizador", "C"},
    {"ambient_air_c", "Temp. ambiente", "C"},
    {"coolant_level_pct", "Nivel refrigerante", "%"},
    {"oil_level_pct", "Nivel aceite", "%"},
    {"tire_fl_kpa", "Presion neumatico DI", "kPa"},
    {"tire_fr_kpa", "Presion neumatico DD", "kPa"},
    {"tire_rl_kpa", "Presion neumatico TI", "kPa"},
    {"tire_rr_kpa", "Presion neumatico TD", "kPa"},
    {NULL, NULL, NULL}
};

typedef enum {
    AGG_NONE = 0,
    AGG_AVG,
    AGG_MIN,
    AGG_MAX,
    AGG_SUM,
    AGG_COUNT
} Agg;

static const Metric *find_metric(const char *name)
{
    for (const Metric *m = METRICS; m->name; m++) {
        if (strcmp(m->name, name) == 0) {
            return m;
        }
    }
    return NULL;
}

static void print_json_string(FILE *out, const char *text)
{
    const unsigned char *p = (const unsigned char *)(text ? text : "");
    fputc('"', out);
    while (*p) {
        switch (*p) {
        case '"':
            fputs("\\\"", out);
            break;
        case '\\':
            fputs("\\\\", out);
            break;
        case '\b':
            fputs("\\b", out);
            break;
        case '\f':
            fputs("\\f", out);
            break;
        case '\n':
            fputs("\\n", out);
            break;
        case '\r':
            fputs("\\r", out);
            break;
        case '\t':
            fputs("\\t", out);
            break;
        default:
            if (*p < 0x20) {
                fprintf(out, "\\u%04x", *p);
            } else {
                fputc(*p, out);
            }
            break;
        }
        p++;
    }
    fputc('"', out);
}

static void print_json_value(sqlite3_stmt *stmt, int col)
{
    switch (sqlite3_column_type(stmt, col)) {
    case SQLITE_INTEGER:
        printf("%" PRId64, (int64_t)sqlite3_column_int64(stmt, col));
        break;
    case SQLITE_FLOAT: {
        double v = sqlite3_column_double(stmt, col);
        if (isnan(v) || isinf(v)) {
            printf("null");
        } else {
            printf("%.10g", v);
        }
        break;
    }
    case SQLITE_TEXT:
        print_json_string(stdout, (const char *)sqlite3_column_text(stmt, col));
        break;
    default:
        printf("null");
        break;
    }
}

static void print_csv_text(const char *text)
{
    if (!text) {
        return;
    }
    if (strchr(text, ',') || strchr(text, '"') || strchr(text, '\n') || strchr(text, '\r')) {
        fputc('"', stdout);
        for (const char *p = text; *p; p++) {
            if (*p == '"') {
                fputc('"', stdout);
            }
            fputc(*p, stdout);
        }
        fputc('"', stdout);
    } else {
        fputs(text, stdout);
    }
}

static void print_csv_value(sqlite3_stmt *stmt, int col)
{
    if (sqlite3_column_type(stmt, col) == SQLITE_NULL) {
        return;
    }
    print_csv_text((const char *)sqlite3_column_text(stmt, col));
}

static void print_table_value(sqlite3_stmt *stmt, int col)
{
    const char *text;
    char buf[42];
    if (sqlite3_column_type(stmt, col) == SQLITE_NULL) {
        printf("%-22s", "-");
        return;
    }
    text = (const char *)sqlite3_column_text(stmt, col);
    if (!text) {
        text = "";
    }
    snprintf(buf, sizeof(buf), "%.40s", text);
    printf("%-22s", buf);
}

static void format_local(int64_t epoch, char *out, size_t cap)
{
    struct tm tm;
    time_t t = (time_t)epoch;
    localtime_r(&t, &tm);
    strftime(out, cap, "%Y-%m-%d %H:%M:%S", &tm);
}

static int parse_time(const char *text, int64_t now, int64_t *out)
{
    char buf[80];
    size_t len;
    int utc = 0;
    struct tm tm;
    const char *rest;
    static const char *formats[] = {
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        NULL
    };

    if (!text || !*text || strcmp(text, "now") == 0) {
        *out = now;
        return 0;
    }
    if (strcmp(text, "today") == 0 || strcmp(text, "hoy") == 0) {
        struct tm local;
        time_t t = (time_t)now;
        localtime_r(&t, &local);
        local.tm_hour = 0;
        local.tm_min = 0;
        local.tm_sec = 0;
        local.tm_isdst = -1;
        *out = (int64_t)mktime(&local);
        return 0;
    }
    if (text[0] == '-' && text[1] >= '0' && text[1] <= '9') {
        char *end = NULL;
        long amount = strtol(text + 1, &end, 10);
        int64_t unit;
        if (!end || !*end || amount < 0) {
            return -1;
        }
        if (strcmp(end, "s") == 0) {
            unit = 1;
        } else if (strcmp(end, "m") == 0) {
            unit = 60;
        } else if (strcmp(end, "h") == 0) {
            unit = 3600;
        } else if (strcmp(end, "d") == 0) {
            unit = 86400;
        } else if (strcmp(end, "w") == 0) {
            unit = 604800;
        } else {
            return -1;
        }
        *out = now - (int64_t)amount * unit;
        return 0;
    }
    len = strlen(text);
    if (len == 0 || len >= sizeof(buf)) {
        return -1;
    }
    memcpy(buf, text, len + 1);
    if (len > 1 && (buf[len - 1] == 'Z' || buf[len - 1] == 'z')) {
        buf[len - 1] = '\0';
        utc = 1;
    }
    for (int i = 0; formats[i]; i++) {
        memset(&tm, 0, sizeof(tm));
        tm.tm_isdst = -1;
        rest = strptime(buf, formats[i], &tm);
        if (rest && *rest == '\0') {
            time_t t = utc ? timegm(&tm) : mktime(&tm);
            *out = (int64_t)t;
            return 0;
        }
    }
    return -1;
}

static int parse_agg(const char *text, Agg *agg)
{
    if (strcmp(text, "none") == 0) {
        *agg = AGG_NONE;
    } else if (strcmp(text, "avg") == 0 || strcmp(text, "promedio") == 0) {
        *agg = AGG_AVG;
    } else if (strcmp(text, "min") == 0 || strcmp(text, "minimo") == 0) {
        *agg = AGG_MIN;
    } else if (strcmp(text, "max") == 0 || strcmp(text, "maximo") == 0) {
        *agg = AGG_MAX;
    } else if (strcmp(text, "sum") == 0 || strcmp(text, "suma") == 0) {
        *agg = AGG_SUM;
    } else if (strcmp(text, "count") == 0 || strcmp(text, "cuenta") == 0) {
        *agg = AGG_COUNT;
    } else {
        return -1;
    }
    return 0;
}

static const char *agg_name(Agg agg)
{
    switch (agg) {
    case AGG_AVG:
        return "avg";
    case AGG_MIN:
        return "min";
    case AGG_MAX:
        return "max";
    case AGG_SUM:
        return "sum";
    case AGG_COUNT:
        return "count";
    default:
        return "none";
    }
}

static void usage(const char *name)
{
    printf("uso: %s [opciones]\n", name);
    printf("  --db RUTA          base SQLite (default: data/vehicle.db)\n");
    printf("  --metric NOMBRE    metrica o 'all'/'raw' (default: all)\n");
    printf("  --agg TIPO         none|avg|min|max|sum|count (default: none)\n");
    printf("  --from TIEMPO      -60m, -24h, -7d, today, ISO (default: -60m)\n");
    printf("  --to TIEMPO        now o ISO (default: now)\n");
    printf("  --last N           ultimas N muestras, ignora from/to\n");
    printf("  --limit N          maximo de filas (default: 20)\n");
    printf("  --order asc|desc   orden por epoch (default: desc)\n");
    printf("  --format json|csv|table (default: table)\n");
    printf("  --list-metrics     lista metricas disponibles\n");
    printf("  --help             esta ayuda\n");
}

int main(int argc, char **argv)
{
    const char *db_path = "data/vehicle.db";
    const char *metric = "all";
    const char *from_text = "-60m";
    const char *to_text = "now";
    const char *format = "table";
    Agg agg = AGG_NONE;
    int limit = 20;
    int last = 0;
    int order_desc = 1;
    int list_metrics = 0;
    static const struct option options[] = {
        {"db", required_argument, NULL, 'd'},
        {"metric", required_argument, NULL, 'm'},
        {"agg", required_argument, NULL, 'a'},
        {"from", required_argument, NULL, 'f'},
        {"to", required_argument, NULL, 't'},
        {"last", required_argument, NULL, 'l'},
        {"limit", required_argument, NULL, 'n'},
        {"order", required_argument, NULL, 'o'},
        {"format", required_argument, NULL, 'F'},
        {"list-metrics", no_argument, NULL, 'L'},
        {"help", no_argument, NULL, 'h'},
        {NULL, 0, NULL, 0}
    };
    int opt;
    int64_t now;
    int64_t from_epoch;
    int64_t to_epoch;
    char *sql = NULL;
    sqlite3 *db = NULL;
    sqlite3_stmt *stmt = NULL;
    int rc;
    int row_count = 0;

    while ((opt = getopt_long(argc, argv, "d:m:a:f:t:l:n:o:F:Lh", options, NULL)) != -1) {
        switch (opt) {
        case 'd':
            db_path = optarg;
            break;
        case 'm':
            metric = optarg;
            break;
        case 'a':
            if (parse_agg(optarg, &agg) != 0) {
                fprintf(stderr, "agregacion invalida: %s\n", optarg);
                return 2;
            }
            break;
        case 'f':
            from_text = optarg;
            break;
        case 't':
            to_text = optarg;
            break;
        case 'l':
            last = atoi(optarg);
            break;
        case 'n':
            limit = atoi(optarg);
            break;
        case 'o':
            if (strcmp(optarg, "asc") == 0) {
                order_desc = 0;
            } else if (strcmp(optarg, "desc") == 0) {
                order_desc = 1;
            } else {
                fprintf(stderr, "orden invalido: %s\n", optarg);
                return 2;
            }
            break;
        case 'F':
            format = optarg;
            break;
        case 'L':
            list_metrics = 1;
            break;
        case 'h':
            usage(argv[0]);
            return 0;
        default:
            usage(argv[0]);
            return 2;
        }
    }

    if (list_metrics) {
        for (const Metric *m = METRICS; m->name; m++) {
            printf("%s\t%s\t%s\n", m->name, m->label, m->unit);
        }
        return 0;
    }
    if (limit < 1) {
        limit = 1;
    }
    if (limit > 1000) {
        limit = 1000;
    }
    if (last < 0) {
        last = 0;
    }
    if (strcmp(format, "json") != 0 && strcmp(format, "csv") != 0 && strcmp(format, "table") != 0) {
        fprintf(stderr, "formato invalido: %s\n", format);
        return 2;
    }
    if (strcmp(metric, "all") != 0 && strcmp(metric, "raw") != 0 && !find_metric(metric)) {
        fprintf(stderr, "metrica invalida: %s\n", metric);
        return 2;
    }
    if (agg != AGG_NONE && agg != AGG_COUNT &&
        (strcmp(metric, "all") == 0 || strcmp(metric, "raw") == 0)) {
        fprintf(stderr, "las agregaciones requieren una metrica concreta\n");
        return 2;
    }

    now = (int64_t)time(NULL);
    if (parse_time(from_text, now, &from_epoch) != 0) {
        fprintf(stderr, "fecha from invalida: %s\n", from_text);
        return 2;
    }
    if (parse_time(to_text, now, &to_epoch) != 0) {
        fprintf(stderr, "fecha to invalida: %s\n", to_text);
        return 2;
    }
    if (from_epoch > to_epoch) {
        fprintf(stderr, "from es posterior a to\n");
        return 2;
    }

    if (db_path && strcmp(db_path, ":memory:") != 0) {
        char *slash = strrchr(db_path, '/');
        if (slash) {
            char parent[1024];
            size_t n = (size_t)(slash - db_path);
            if (n >= sizeof(parent)) {
                fprintf(stderr, "ruta de base demasiado larga\n");
                return 2;
            }
            memcpy(parent, db_path, n);
            parent[n] = '\0';
            (void)parent;
        }
    }
    rc = sqlite3_open_v2(db_path, &db, SQLITE_OPEN_READONLY, NULL);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "no se pudo abrir %s: %s\n", db_path, db ? sqlite3_errmsg(db) : "sin detalle");
        if (db) {
            sqlite3_close(db);
        }
        return 3;
    }
    sqlite3_busy_timeout(db, 5000);

    const char *order = order_desc ? "DESC" : "ASC";
    char where[256];
    char metric_filter[512];
    const char *metric_where = where;
    if (last > 0) {
        where[0] = '\0';
        limit = last;
    } else {
        snprintf(where, sizeof(where), " WHERE epoch >= %" PRId64 " AND epoch <= %" PRId64,
                 from_epoch, to_epoch);
    }
    if (agg == AGG_NONE && strcmp(metric, "all") != 0 && strcmp(metric, "raw") != 0) {
        if (where[0]) {
            snprintf(metric_filter, sizeof(metric_filter), "%s AND %s IS NOT NULL",
                     where, metric);
        } else {
            snprintf(metric_filter, sizeof(metric_filter), " WHERE %s IS NOT NULL", metric);
        }
        metric_where = metric_filter;
    }

    if (agg == AGG_NONE) {
        if (strcmp(metric, "all") == 0) {
            sql = sqlite3_mprintf(
                "SELECT ts_utc, epoch, source, pid_count, speed_kph, rpm, coolant_c,"
                " engine_load_pct, throttle_pct, fuel_level_pct, intake_air_c, maf_gps,"
                " fuel_pressure_kpa, map_kpa, timing_advance_deg, run_time_s, battery_v,"
                " oil_temp_c, barometric_kpa, short_fuel_trim_pct, long_fuel_trim_pct,"
                " catalyst_temp_c, ambient_air_c, coolant_level_pct, oil_level_pct,"
                " tire_fl_kpa, tire_fr_kpa, tire_rl_kpa, tire_rr_kpa,"
                " dtc_codes, warning_flags FROM vehicle_samples%s"
                " ORDER BY epoch %s LIMIT %d",
                where, order, limit);
        } else if (strcmp(metric, "raw") == 0) {
            sql = sqlite3_mprintf(
                "SELECT ts_utc, epoch, source, raw_json FROM vehicle_samples%s"
                " ORDER BY epoch %s LIMIT %d",
                where, order, limit);
        } else {
            sql = sqlite3_mprintf(
                "SELECT ts_utc, epoch, %s FROM vehicle_samples%s"
                " ORDER BY epoch %s LIMIT %d",
                metric, metric_where, order, limit);
        }
    } else if (agg == AGG_COUNT) {
        sql = sqlite3_mprintf("SELECT COUNT(*) AS n FROM vehicle_samples%s", where);
    } else if (agg == AGG_AVG) {
        sql = sqlite3_mprintf("SELECT COUNT(%s) AS n, AVG(%s) AS value FROM vehicle_samples%s",
                              metric, metric, where);
    } else if (agg == AGG_SUM) {
        sql = sqlite3_mprintf("SELECT COUNT(%s) AS n, SUM(%s) AS value FROM vehicle_samples%s",
                              metric, metric, where);
    } else if (agg == AGG_MIN) {
        sql = sqlite3_mprintf(
            "SELECT ts_utc, epoch, %s AS value FROM vehicle_samples%s"
            " AND %s IS NOT NULL ORDER BY %s ASC LIMIT 1",
            metric, where, metric, metric);
        if (where[0] == '\0') {
            sqlite3_free(sql);
            sql = sqlite3_mprintf(
                "SELECT ts_utc, epoch, %s AS value FROM vehicle_samples"
                " WHERE %s IS NOT NULL ORDER BY %s ASC LIMIT 1",
                metric, metric, metric);
        }
    } else if (agg == AGG_MAX) {
        sql = sqlite3_mprintf(
            "SELECT ts_utc, epoch, %s AS value FROM vehicle_samples%s"
            " AND %s IS NOT NULL ORDER BY %s DESC LIMIT 1",
            metric, where, metric, metric);
        if (where[0] == '\0') {
            sqlite3_free(sql);
            sql = sqlite3_mprintf(
                "SELECT ts_utc, epoch, %s AS value FROM vehicle_samples"
                " WHERE %s IS NOT NULL ORDER BY %s DESC LIMIT 1",
                metric, metric, metric);
        }
    }

    if (!sql) {
        sqlite3_close(db);
        return 3;
    }
    rc = sqlite3_prepare_v2(db, sql, -1, &stmt, NULL);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "consulta invalida: %s\n", sqlite3_errmsg(db));
        sqlite3_free(sql);
        sqlite3_close(db);
        return 3;
    }

    if (strcmp(format, "json") == 0) {
        char from_local[32];
        char to_local[32];
        format_local(from_epoch, from_local, sizeof(from_local));
        format_local(to_epoch, to_local, sizeof(to_local));
        printf("{\"ok\":true,\"query\":{\"metric\":");
        print_json_string(stdout, metric);
        printf(",\"agg\":");
        print_json_string(stdout, agg_name(agg));
        printf(",\"from\":");
        print_json_string(stdout, from_text);
        printf(",\"to\":");
        print_json_string(stdout, to_text);
        printf(",\"from_epoch\":%" PRId64 ",\"to_epoch\":%" PRId64
               ",\"from_local\":", from_epoch, to_epoch);
        print_json_string(stdout, from_local);
        printf(",\"to_local\":");
        print_json_string(stdout, to_local);
        printf(",\"limit\":%d,\"order\":", limit);
        print_json_string(stdout, order_desc ? "desc" : "asc");
        printf(",\"db\":");
        print_json_string(stdout, db_path);
        printf("},\"columns\":[");
        int cols = sqlite3_column_count(stmt);
        for (int i = 0; i < cols; i++) {
            if (i) {
                printf(",");
            }
            print_json_string(stdout, sqlite3_column_name(stmt, i));
        }
        printf("],\"rows\":[");
        int first = 1;
        while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
            if (!first) {
                printf(",");
            }
            first = 0;
            printf("{");
            for (int i = 0; i < cols; i++) {
                if (i) {
                    printf(",");
                }
                print_json_string(stdout, sqlite3_column_name(stmt, i));
                printf(":");
                print_json_value(stmt, i);
            }
            printf("}");
            row_count++;
        }
        printf("],\"row_count\":%d}\n", row_count);
        if (rc != SQLITE_DONE) {
            fprintf(stderr, "error recorriendo resultados: %s\n", sqlite3_errmsg(db));
        }
    } else if (strcmp(format, "csv") == 0) {
        int cols = sqlite3_column_count(stmt);
        for (int i = 0; i < cols; i++) {
            if (i) {
                printf(",");
            }
            print_csv_text(sqlite3_column_name(stmt, i));
        }
        printf("\n");
        while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
            for (int i = 0; i < cols; i++) {
                if (i) {
                    printf(",");
                }
                print_csv_value(stmt, i);
            }
            printf("\n");
            row_count++;
        }
    } else {
        int cols = sqlite3_column_count(stmt);
        for (int i = 0; i < cols; i++) {
            char name[42];
            snprintf(name, sizeof(name), "%.40s", sqlite3_column_name(stmt, i));
            printf("%-22s", name);
        }
        printf("\n");
        for (int i = 0; i < cols; i++) {
            printf("%-22s", "----------------------");
        }
        printf("\n");
        while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
            for (int i = 0; i < cols; i++) {
                print_table_value(stmt, i);
            }
            printf("\n");
            row_count++;
        }
    }

    if (strcmp(format, "json") != 0) {
        fprintf(stderr, "filas: %d\n", row_count);
    }
    sqlite3_finalize(stmt);
    sqlite3_free(sql);
    sqlite3_close(db);
    return 0;
}
