#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static int64_t now(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) abort();
    return (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    char *end;
    int64_t ms = strtoll(argv[1], &end, 10);
    if (*end || ms <= 0 || ms > 1000) return 2;
    int64_t start = now(), target = start + ms * 1000000;
    struct timespec finish = { target / 1000000000, target % 1000000000 };
    if (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &finish, NULL) != 0) return 4;
    if (printf("%" PRId64 " %" PRId64 "\n", start, now()) < 0) return 5;
    return 0;
}
