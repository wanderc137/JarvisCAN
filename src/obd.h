#ifndef JARVIS_CAN_OBD_H
#define JARVIS_CAN_OBD_H

#include <stdint.h>
#include <net/if.h>

typedef struct {
    int fd;
    int is_sim;
    char ifname[128];
} ObdLink;

int obd_open(ObdLink *link, const char *ifname, int timeout_ms);
void obd_close(ObdLink *link);
int obd_read_pid(ObdLink *link, uint8_t pid, uint8_t *out, int maxlen);

#endif
