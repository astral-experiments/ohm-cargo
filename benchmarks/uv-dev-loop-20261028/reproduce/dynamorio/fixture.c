#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static void *spin(void *count) {
    uintptr_t n = (uintptr_t)count;
    /* Exactly two instructions per additional iteration. */
    __asm__ volatile("1: decq %0\n\tjnz 1b" : "+r"(n) : : "cc");
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 4)
        return 1;
    uintptr_t iterations = strtoul(argv[1], NULL, 10);
    uintptr_t workers = strtoul(argv[2], NULL, 10);
    if (iterations == 0 || workers > 8)
        return 1;
    if (strcmp(argv[3], "exec") == 0) {
        pid_t pid = fork();
        if (pid == -1)
            return 2;
        if (pid == 0) {
            argv[3] = "spin";
            execv(argv[0], argv);
            _exit(3);
        }
        int rc;
        if (waitpid(pid, &rc, 0) != pid)
            return 4;
        return WIFEXITED(rc) ? WEXITSTATUS(rc) : 5;
    }
    if (strcmp(argv[3], "spin") != 0)
        return 1;
    pthread_t thread[8];
    for (uintptr_t i = 0; i < workers; ++i) {
        if (pthread_create(&thread[i], NULL, spin, (void *)iterations))
            return 6;
    }
    for (uintptr_t i = 0; i < workers; ++i) {
        if (pthread_join(thread[i], NULL))
            return 7;
    }
    return 0;
}
