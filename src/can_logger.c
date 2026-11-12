#define _GNU_SOURCE
#include "db.h"
#include "obd.h"

#include <errno.h>
#include <getopt.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t g_stop = 0;

static void on_signal(int signum)
{
    (void)signum;
    g_stop = 1;
}

static void iso_utc(int64_t epoch, char *out, size_t cap)
{
    struct tm tm;
    time_t t = (time_t)epoch;
    gmtime_r(&t, &tm);
    strftime(out, cap, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

static void sample_init(VehicleSample *s)
{
    memset(s, 0, sizeof(*s));
    s->speed_kph = NAN;
    s->rpm = NAN;
    s->coolant_c = NAN;
    s->engine_load_pct = NAN;
    s->throttle_pct = NAN;
    s->fuel_level_pct = NAN;
    s->intake_air_c = NAN;
    s->maf_gps = NAN;
    s->fuel_pressure_kpa = NAN;
    s->map_kpa = NAN;
    s->timing_advance_deg = NAN;
    s->run_time_s = NAN;
    s->battery_v = NAN;
    s->oil_temp_c = NAN;
    s->barometric_kpa = NAN;
    s->short_fuel_trim_pct = NAN;
    s->long_fuel_trim_pct = NAN;
    s->catalyst_temp_c = NAN;
    s->ambient_air_c = NAN;
    s->coolant_level_pct = NAN;
    s->oil_level_pct = NAN;
    s->tire_fl_kpa = NAN;
    s->tire_fr_kpa = NAN;
    s->tire_rl_kpa = NAN;
    s->tire_rr_kpa = NAN;
    s->dtc_codes[0] = '\0';
    s->warning_flags[0] = '\0';
    strcpy(s->raw_json, "{}");
}

static void json_add_number(char *buf, size_t cap, size_t *used, int *first,
                            const char *key, double value)
{
    char num[64];
    int n;
    if (isnan(value)) {
        strcpy(num, "null");
    } else {
        snprintf(num, sizeof(num), "%.3f", value);
    }
    n = snprintf(buf + *used, cap - *used, "%s\"%s\":%s",
                 *first ? "" : ",", key, num);
    if (n > 0 && (size_t)n < cap - *used) {
        *used += (size_t)n;
    }
    *first = 0;
}

static void build_raw_json(VehicleSample *s)
{
    size_t used = 0;
    int first = 1;
    int n = snprintf(s->raw_json, sizeof(s->raw_json),
                     "{\"source\":\"%s\",\"pid_count\":%d",
                     s->source, s->pid_count);
    if (n > 0 && (size_t)n < sizeof(s->raw_json)) {
        used = (size_t)n;
    }
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "speed_kph", s->speed_kph);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "rpm", s->rpm);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "coolant_c", s->coolant_c);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "engine_load_pct", s->engine_load_pct);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "throttle_pct", s->throttle_pct);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "fuel_level_pct", s->fuel_level_pct);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "intake_air_c", s->intake_air_c);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "maf_gps", s->maf_gps);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "fuel_pressure_kpa", s->fuel_pressure_kpa);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "map_kpa", s->map_kpa);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "timing_advance_deg", s->timing_advance_deg);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "run_time_s", s->run_time_s);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "battery_v", s->battery_v);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "oil_temp_c", s->oil_temp_c);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "barometric_kpa", s->barometric_kpa);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "short_fuel_trim_pct", s->short_fuel_trim_pct);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "long_fuel_trim_pct", s->long_fuel_trim_pct);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "catalyst_temp_c", s->catalyst_temp_c);
    json_add_number(s->raw_json, sizeof(s->raw_json), &used, &first, "ambient_air_c", s->ambient_air_c);
    if (used + 2 < sizeof(s->raw_json)) {
        s->raw_json[used++] = '}';
        s->raw_json[used] = '\0';
    }
}

static double walk_value(double *state, double min, double max, double step)
{
    double delta = ((double)rand() / (double)RAND_MAX - 0.5) * 2.0 * step;
    *state += delta;
    if (*state < min) {
        *state = min;
    }
    if (*state > max) {
        *state = max;
    }
    return *state;
}

static void simulate_sample(VehicleSample *s)
{
    static int initialized = 0;
    static double speed = 35.0;
    static double rpm = 1800.0;
    static double coolant = 88.0;
    static double load = 35.0;
    static double throttle = 18.0;
    static double fuel = 62.0;
    static double intake = 32.0;
    static double maf = 8.0;
    static double fuel_pressure = 320.0;
    static double map = 45.0;
    static double timing = 18.0;
    static double battery = 13.9;
    static double oil = 92.0;
    static double barometric = 101.0;
    static double stft = 1.5;
    static double ltft = -2.0;
    static double catalyst = 480.0;
    static double ambient = 24.0;
    static double run_time = 0.0;

    if (!initialized) {
        srand((unsigned)time(NULL) ^ (unsigned)getpid());
        initialized = 1;
    }
    speed = walk_value(&speed, 0.0, 130.0, 6.0);
    rpm = walk_value(&rpm, 650.0, 4200.0, 260.0);
    coolant = walk_value(&coolant, 70.0, 105.0, 0.8);
    load = walk_value(&load, 5.0, 95.0, 5.0);
    throttle = walk_value(&throttle, 0.0, 85.0, 6.0);
    fuel = walk_value(&fuel, 5.0, 100.0, 0.3);
    intake = walk_value(&intake, 15.0, 65.0, 1.5);
    maf = walk_value(&maf, 1.5, 30.0, 1.2);
    fuel_pressure = walk_value(&fuel_pressure, 250.0, 420.0, 8.0);
    map = walk_value(&map, 25.0, 100.0, 4.0);
    timing = walk_value(&timing, 0.0, 42.0, 1.5);
    battery = walk_value(&battery, 12.0, 14.8, 0.1);
    oil = walk_value(&oil, 65.0, 115.0, 0.8);
    barometric = walk_value(&barometric, 99.0, 103.0, 0.1);
    stft = walk_value(&stft, -15.0, 15.0, 1.2);
    ltft = walk_value(&ltft, -15.0, 15.0, 0.8);
    catalyst = walk_value(&catalyst, 300.0, 850.0, 18.0);
    ambient = walk_value(&ambient, 8.0, 38.0, 0.4);
    run_time += 60.0;

    s->speed_kph = speed;
    s->rpm = rpm;
    s->coolant_c = coolant;
    s->engine_load_pct = load;
    s->throttle_pct = throttle;
    s->fuel_level_pct = fuel;
    s->intake_air_c = intake;
    s->maf_gps = maf;
    s->fuel_pressure_kpa = fuel_pressure;
    s->map_kpa = map;
    s->timing_advance_deg = timing;
    s->run_time_s = run_time;
    s->battery_v = battery;
    s->oil_temp_c = oil;
    s->barometric_kpa = barometric;
    s->short_fuel_trim_pct = stft;
    s->long_fuel_trim_pct = ltft;
    s->catalyst_temp_c = catalyst;
    s->ambient_air_c = ambient;
    s->pid_count = 18;
    strcpy(s->source, "simulator");
}

static int collect_obd(VehicleSample *s, const char *ifname, int timeout_ms, int verbose)
{
    ObdLink link;
    uint8_t d[8];
    int n;
    int count = 0;

    if (obd_open(&link, ifname, timeout_ms) != 0) {
        return -1;
    }
    strcpy(s->source, "obd");

    n = obd_read_pid(&link, 0x04, d, sizeof(d));
    if (n >= 1) {
        s->engine_load_pct = d[0] * 100.0 / 255.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 04 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x05, d, sizeof(d));
    if (n >= 1) {
        s->coolant_c = (double)d[0] - 40.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 05 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x06, d, sizeof(d));
    if (n >= 1) {
        s->short_fuel_trim_pct = (double)d[0] / 1.28 - 100.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 06 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x07, d, sizeof(d));
    if (n >= 1) {
        s->long_fuel_trim_pct = (double)d[0] / 1.28 - 100.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 07 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x0A, d, sizeof(d));
    if (n >= 1) {
        s->fuel_pressure_kpa = (double)d[0] * 3.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 0A sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x0B, d, sizeof(d));
    if (n >= 1) {
        s->map_kpa = (double)d[0];
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 0B sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x0C, d, sizeof(d));
    if (n >= 2) {
        s->rpm = ((double)d[0] * 256.0 + (double)d[1]) / 4.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 0C sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x0D, d, sizeof(d));
    if (n >= 1) {
        s->speed_kph = (double)d[0];
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 0D sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x0E, d, sizeof(d));
    if (n >= 1) {
        s->timing_advance_deg = (double)d[0] / 2.0 - 64.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 0E sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x0F, d, sizeof(d));
    if (n >= 1) {
        s->intake_air_c = (double)d[0] - 40.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 0F sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x10, d, sizeof(d));
    if (n >= 2) {
        s->maf_gps = ((double)d[0] * 256.0 + (double)d[1]) / 100.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 10 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x11, d, sizeof(d));
    if (n >= 1) {
        s->throttle_pct = d[0] * 100.0 / 255.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 11 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x1F, d, sizeof(d));
    if (n >= 2) {
        s->run_time_s = (double)d[0] * 256.0 + (double)d[1];
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 1F sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x2F, d, sizeof(d));
    if (n >= 1) {
        s->fuel_level_pct = d[0] * 100.0 / 255.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 2F sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x33, d, sizeof(d));
    if (n >= 1) {
        s->barometric_kpa = (double)d[0];
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 33 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x3C, d, sizeof(d));
    if (n >= 2) {
        s->catalyst_temp_c = ((double)d[0] * 256.0 + (double)d[1]) / 10.0 - 40.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 3C sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x42, d, sizeof(d));
    if (n >= 2) {
        s->battery_v = ((double)d[0] * 256.0 + (double)d[1]) / 1000.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 42 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x46, d, sizeof(d));
    if (n >= 1) {
        s->ambient_air_c = (double)d[0] - 40.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 46 sin respuesta\n");
    }

    n = obd_read_pid(&link, 0x5C, d, sizeof(d));
    if (n >= 1) {
        s->oil_temp_c = (double)d[0] - 40.0;
        count++;
    } else if (verbose) {
        fprintf(stderr, "PID 5C sin respuesta\n");
    }

    obd_close(&link);
    s->pid_count = count;
    if (count == 0) {
        fprintf(stderr, "sin respuestas OBD-II en %s\n", ifname);
        return -1;
    }
    return 0;
}

static void sleep_until(int64_t epoch)
{
    struct timespec ts;
    ts.tv_sec = (time_t)epoch;
    ts.tv_nsec = 0;
    while (!g_stop) {
        int rc = clock_nanosleep(CLOCK_REALTIME, TIMER_ABSTIME, &ts, NULL);
        if (rc == 0) {
            return;
        }
        if (rc != EINTR) {
            sleep(1);
            return;
        }
    }
}

static void usage(const char *name)
{
    printf("uso: %s [opciones]\n", name);
    printf("  --db RUTA          base SQLite (default: data/vehicle.db)\n");
    printf("  --iface FUENTE     interfaz SocketCAN o unix:/ruta/socket (default: can0)\n");
    printf("  --interval N       segundos entre muestras (default: 60)\n");
    printf("  --timeout MS       timeout por PID (default: 200)\n");
    printf("  --simulate         genera datos simulados, sin CAN\n");
    printf("  --once             toma una sola muestra y termina\n");
    printf("  --verbose          detalle por PID\n");
    printf("  --version          version\n");
    printf("  --help             esta ayuda\n");
}

int main(int argc, char **argv)
{
    const char *db_path = "data/vehicle.db";
    const char *ifname = "can0";
    int interval = 60;
    int timeout_ms = 200;
    int simulate = 0;
    int once = 0;
    int verbose = 0;
    sqlite3 *db = NULL;
    int rc = 0;
    static const struct option options[] = {
        {"db", required_argument, NULL, 'd'},
        {"iface", required_argument, NULL, 'i'},
        {"interval", required_argument, NULL, 'n'},
        {"timeout", required_argument, NULL, 't'},
        {"simulate", no_argument, NULL, 's'},
        {"once", no_argument, NULL, '1'},
        {"verbose", no_argument, NULL, 'v'},
        {"version", no_argument, NULL, 'V'},
        {"help", no_argument, NULL, 'h'},
        {NULL, 0, NULL, 0}
    };
    int opt;

    while ((opt = getopt_long(argc, argv, "d:i:n:t:s1vVh", options, NULL)) != -1) {
        switch (opt) {
        case 'd':
            db_path = optarg;
            break;
        case 'i':
            ifname = optarg;
            break;
        case 'n':
            interval = atoi(optarg);
            if (interval < 1) {
                interval = 1;
            }
            break;
        case 't':
            timeout_ms = atoi(optarg);
            if (timeout_ms < 20) {
                timeout_ms = 20;
            }
            break;
        case 's':
            simulate = 1;
            break;
        case '1':
            once = 1;
            break;
        case 'v':
            verbose = 1;
            break;
        case 'V':
            printf("can_logger 1.0.0\n");
            return 0;
        case 'h':
            usage(argv[0]);
            return 0;
        default:
            usage(argv[0]);
            return 2;
        }
    }

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    if (db_open(db_path, &db) != 0) {
        return 1;
    }
    if (db_init(db) != 0) {
        db_close(db);
        return 1;
    }

    int64_t next = (int64_t)time(NULL);
    while (!g_stop) {
        VehicleSample sample;
        sample_init(&sample);
        sample.epoch = (int64_t)time(NULL);
        iso_utc(sample.epoch, sample.ts_utc, sizeof(sample.ts_utc));

        if (simulate) {
            simulate_sample(&sample);
        } else if (collect_obd(&sample, ifname, timeout_ms, verbose) != 0) {
            fprintf(stderr, "%s: no se pudo leer OBD-II\n", sample.ts_utc);
            rc = 1;
            if (once) {
                break;
            }
        }

        if (sample.pid_count > 0) {
            build_raw_json(&sample);
            if (db_insert(db, &sample) == 0) {
                if (verbose) {
                    printf("%s source=%s pids=%d speed=%.1f rpm=%.0f coolant=%.1f\n",
                           sample.ts_utc, sample.source, sample.pid_count,
                           sample.speed_kph, sample.rpm, sample.coolant_c);
                }
                rc = 0;
            } else {
                rc = 1;
            }
        } else if (!once) {
            fprintf(stderr, "%s: muestra vacia, no se inserta\n", sample.ts_utc);
        }

        if (once) {
            break;
        }
        next += interval;
        int64_t now = (int64_t)time(NULL);
        if (next <= now) {
            next = now + interval;
        }
        sleep_until(next);
    }

    db_close(db);
    return rc;
}
