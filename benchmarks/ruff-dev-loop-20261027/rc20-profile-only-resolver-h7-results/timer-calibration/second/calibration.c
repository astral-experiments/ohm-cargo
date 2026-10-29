#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
static int64_t now(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) abort();
    return (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    int fd = open(argv[2], O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    struct stat s;
    if (fd < 0 || fstat(fd, &s) < 0 || !S_ISREG(s.st_mode) || s.st_size != 4096 || s.st_nlink != 1) abort();
    volatile int64_t *page = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if ((void*)page == MAP_FAILED || close(fd) != 0) abort();
    page[0] = -1; page[1] = -1;
    char *end;
    int64_t ms = strtoll(argv[1], &end, 10);
    if (*end || ms <= 0 || ms > 1000) return 2;
    int64_t start = now(), target = start + ms * 1000000;
    page[0] = start;
    struct timespec finish = { target / 1000000000, target % 1000000000 };
    if (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &finish, NULL) != 0) return 4;
    page[1] = now();
    _exit(0);
}
