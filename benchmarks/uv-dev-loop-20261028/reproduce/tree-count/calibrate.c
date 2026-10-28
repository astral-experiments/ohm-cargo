/* Cargo -> rustc -> Wild, with one separately forked, unmeasured child. */
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static void *spin(void *arg) {
    uintptr_t n = (uintptr_t)arg;
    __asm__ volatile("1: decq %0\n\tjnz 1b" : "+r"(n) : : "cc");
    return NULL;
}

static int join(pid_t pid) {
    int s;
    return pid < 0 || waitpid(pid, &s, 0) != pid || !WIFEXITED(s) || WEXITSTATUS(s);
}

int main(int argc, char **argv) {
    if (argc != 4 || fcntl(atoi(getenv("OHM_CAL_FD")), F_GETFD) < 0)
        return 1;
    char *role = argv[1];
    uintptr_t n = strtoul(argv[2], NULL, 10), outside = strtoul(argv[3], NULL, 10);
    if (!n || !outside)
        return 2;
    if (strcmp(role, "wild") != 0) {
        char *next = strcmp(role, "cargo") == 0 ? "rustc" : "wild";
        pid_t pid = fork();
        if (pid == 0) {
            /* Work before exec is intentionally outside this metric. */
            spin((void *)outside);
            char *wrap = getenv("OHM_CAL_WRAPPER");
            execl(wrap, wrap, next, argv[0], next, argv[2], argv[3], (char *)NULL);
            _exit(3);
        }
        if (join(pid))
            return 4;
    }
    if (strcmp(role, "wild") == 0) {
        pthread_t t;
        if (pthread_create(&t, NULL, spin, (void *)n) || pthread_join(t, NULL))
            return 5;
    }
    spin((void *)n);
    return 0;
}
