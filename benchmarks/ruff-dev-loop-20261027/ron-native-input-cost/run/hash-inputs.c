#include "blake3.h"
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

struct input { const char *path; uint8_t digest[BLAKE3_OUT_LEN]; };
static struct input *inputs;
static int count;
static atomic_int cursor;

static void *hash_inputs(void *unused) {
    (void)unused;
    for (;;) {
        int current = atomic_fetch_add(&cursor, 1);
        if (current >= count) return NULL;
        struct input *input = &inputs[current];
        int fd = open(input->path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        struct stat st;
        if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode)) { perror(input->path); exit(2); }
        blake3_hasher hasher;
        blake3_hasher_init(&hasher);
        if (st.st_size) {
            void *p = mmap(NULL, st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
            if (p == MAP_FAILED) { perror("mmap"); exit(3); }
            blake3_hasher_update(&hasher, p, st.st_size);
            if (munmap(p, st.st_size)) { perror("munmap"); exit(4); }
        }
        blake3_hasher_finalize(&hasher, input->digest, BLAKE3_OUT_LEN);
        if (close(fd)) { perror("close"); exit(5); }
    }
}

int main(int argc, char **argv) {
    count = argc - 1;
    if (count < 1) return 1;
    inputs = calloc(count, sizeof *inputs);
    if (!inputs) return 2;
    for (int i = 0; i < count; i++) inputs[i].path = argv[i + 1];
    pthread_t pool[7];
    for (int i = 0; i < 7; i++) if (pthread_create(&pool[i], NULL, hash_inputs, NULL)) return 6;
    hash_inputs(NULL);
    for (int i = 0; i < 7; i++) if (pthread_join(pool[i], NULL)) return 7;
    for (int i = 0; i < count; i++) {
        for (int b = 0; b < BLAKE3_OUT_LEN; b++) printf("%02x", inputs[i].digest[b]);
        putchar('\n');
    }
    free(inputs);
    return ferror(stdout) ? 8 : 0;
}
