#define _GNU_SOURCE
#include "obd.h"

#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

#define OBD_REQUEST_ID 0x7DF
#define OBD_RESPONSE_FIRST 0x7E8
#define OBD_RESPONSE_LAST 0x7EF

static int set_read_timeout(int fd, int timeout_ms)
{
    struct timeval tv;
    if (timeout_ms <= 0) {
        timeout_ms = 200;
    }
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    return setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
}

static int obd_open_sim(ObdLink *link, const char *path, int timeout_ms)
{
    struct sockaddr_un addr;
    int fd;

    if (strlen(path) >= sizeof(addr.sun_path)) {
        fprintf(stderr, "ruta de socket demasiado larga: %s\n", path);
        return -1;
    }
    fd = socket(AF_UNIX, SOCK_SEQPACKET, 0);
    if (fd < 0) {
        fprintf(stderr, "socket simulado: %s\n", strerror(errno));
        return -1;
    }
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        fprintf(stderr, "conectar simulador %s: %s\n", path, strerror(errno));
        close(fd);
        return -1;
    }
    if (set_read_timeout(fd, timeout_ms) != 0) {
        fprintf(stderr, "timeout simulador: %s\n", strerror(errno));
        close(fd);
        return -1;
    }
    link->fd = fd;
    link->is_sim = 1;
    snprintf(link->ifname, sizeof(link->ifname), "unix:%s", path);
    return 0;
}

int obd_open(ObdLink *link, const char *ifname, int timeout_ms)
{
    struct sockaddr_can addr;
    struct ifreq ifr;
    int fd;

    if (!link || !ifname || !*ifname) {
        return -1;
    }
    memset(link, 0, sizeof(*link));
    if (strncmp(ifname, "unix:", 5) == 0) {
        return obd_open_sim(link, ifname + 5, timeout_ms);
    }
    fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (fd < 0) {
        fprintf(stderr, "socket CAN: %s\n", strerror(errno));
        return -1;
    }
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, ifname, IFNAMSIZ - 1);
    if (ioctl(fd, SIOCGIFINDEX, &ifr) < 0) {
        fprintf(stderr, "interfaz CAN %s: %s\n", ifname, strerror(errno));
        close(fd);
        return -1;
    }
    memset(&addr, 0, sizeof(addr));
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        fprintf(stderr, "bind CAN %s: %s\n", ifname, strerror(errno));
        close(fd);
        return -1;
    }
    if (set_read_timeout(fd, timeout_ms) != 0) {
        fprintf(stderr, "timeout CAN: %s\n", strerror(errno));
        close(fd);
        return -1;
    }
    link->fd = fd;
    link->is_sim = 0;
    snprintf(link->ifname, sizeof(link->ifname), "%s", ifname);
    return 0;
}

void obd_close(ObdLink *link)
{
    if (link && link->fd >= 0) {
        close(link->fd);
        link->fd = -1;
    }
}

static void drain_socket(int fd)
{
    struct can_frame frame;
    while (read(fd, &frame, sizeof(frame)) > 0) {
    }
}

int obd_read_pid(ObdLink *link, uint8_t pid, uint8_t *out, int maxlen)
{
    struct can_frame request;
    int attempts = 0;

    if (!link || link->fd < 0 || !out || maxlen <= 0) {
        return -1;
    }
    drain_socket(link->fd);
    memset(&request, 0, sizeof(request));
    request.can_id = OBD_REQUEST_ID;
    request.can_dlc = 8;
    request.data[0] = 0x02;
    request.data[1] = 0x01;
    request.data[2] = pid;
    if (write(link->fd, &request, sizeof(request)) != sizeof(request)) {
        return -1;
    }

    while (attempts++ < 4) {
        struct can_frame response;
        ssize_t n = read(link->fd, &response, sizeof(response));
        int len;
        int payload;
        uint32_t id;
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (n != (ssize_t)sizeof(response)) {
            continue;
        }
        if (response.can_id & CAN_ERR_FLAG) {
            continue;
        }
        id = response.can_id & CAN_SFF_MASK;
        if (id < OBD_RESPONSE_FIRST || id > OBD_RESPONSE_LAST) {
            continue;
        }
        if ((response.data[0] & 0xF0) != 0) {
            continue;
        }
        len = response.data[0] & 0x0F;
        if (len < 3) {
            continue;
        }
        if (response.data[1] != 0x41 || response.data[2] != pid) {
            continue;
        }
        payload = len - 2;
        if (payload > maxlen) {
            payload = maxlen;
        }
        memcpy(out, &response.data[3], (size_t)payload);
        return payload;
    }
    return -1;
}
