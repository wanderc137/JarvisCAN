#define _GNU_SOURCE
#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

static volatile sig_atomic_t running = 1;

static void stop(int signum)
{
    (void)signum;
    running = 0;
}

static void respond(int fd, uint8_t pid)
{
    struct can_frame frame;
    uint8_t a = 0;
    uint8_t b = 0;
    int len = 1;

    memset(&frame, 0, sizeof(frame));
    frame.can_id = 0x7E8;
    frame.can_dlc = 8;

    switch (pid) {
    case 0x04:
        a = 128;
        break;
    case 0x05:
        a = 130;
        break;
    case 0x06:
        a = 128;
        break;
    case 0x07:
        a = 126;
        break;
    case 0x0A:
        a = 110;
        break;
    case 0x0B:
        a = 45;
        break;
    case 0x0C:
        a = 0x1C;
        b = 0x20;
        len = 2;
        break;
    case 0x0D:
        a = 60;
        break;
    case 0x0E:
        a = 150;
        break;
    case 0x0F:
        a = 70;
        break;
    case 0x10:
        a = 0x01;
        b = 0xF4;
        len = 2;
        break;
    case 0x11:
        a = 64;
        break;
    case 0x1F:
        a = 0x0E;
        b = 0x10;
        len = 2;
        break;
    case 0x2F:
        a = 160;
        break;
    case 0x33:
        a = 101;
        break;
    case 0x3C:
        a = 0x0B;
        b = 0xB8;
        len = 2;
        break;
    case 0x42:
        a = 0x36;
        b = 0x1E;
        len = 2;
        break;
    case 0x46:
        a = 64;
        break;
    case 0x5C:
        a = 130;
        break;
    default:
        return;
    }

    frame.data[0] = (uint8_t)(2 + len);
    frame.data[1] = 0x41;
    frame.data[2] = pid;
    frame.data[3] = a;
    if (len == 2) {
        frame.data[4] = b;
    }
    (void)write(fd, &frame, sizeof(frame));
}

int main(int argc, char **argv)
{
    const char *ifname = argc > 1 ? argv[1] : "vcan0";
    struct sockaddr_can addr;
    struct ifreq ifr;
    int fd;

    signal(SIGINT, stop);
    signal(SIGTERM, stop);

    fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (fd < 0) {
        perror("socket");
        return 1;
    }
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, ifname, IFNAMSIZ - 1);
    if (ioctl(fd, SIOCGIFINDEX, &ifr) < 0) {
        perror("ioctl");
        close(fd);
        return 1;
    }
    memset(&addr, 0, sizeof(addr));
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(fd);
        return 1;
    }

    fprintf(stderr, "ECU simulada en %s\n", ifname);
    while (running) {
        struct can_frame frame;
        ssize_t n = read(fd, &frame, sizeof(frame));
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("read");
            break;
        }
        if (n != (ssize_t)sizeof(frame)) {
            continue;
        }
        if ((frame.can_id & CAN_SFF_MASK) != 0x7DF || frame.can_dlc < 3) {
            continue;
        }
        if (frame.data[1] == 0x01) {
            respond(fd, frame.data[2]);
        }
    }
    close(fd);
    return 0;
}
