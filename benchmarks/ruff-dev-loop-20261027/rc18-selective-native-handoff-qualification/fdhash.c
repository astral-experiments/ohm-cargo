/* Hash the actual regular descriptor through EOF. A size hint never terminates the loop. */
#define _GNU_SOURCE
#include "blake3.h"
#include "blake3_impl.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

uint32_t link_check_simd_degree(void) { return blake3_simd_degree(); }

int link_check_fd(int fd, unsigned char out[BLAKE3_OUT_LEN], uint64_t *length) {
    struct stat before, after;
    if (fstat(fd, &before) || !S_ISREG(before.st_mode)) return 1;
    size_t cap = 262144;
    void *buf = NULL;
    if (posix_memalign(&buf,64,cap)) return 2;
    blake3_hasher h; blake3_hasher_init(&h);
    off_t offset=0;
    int status=0;
    for (;;) {
        ssize_t n=pread(fd,buf,cap,offset);
        if (!n) break;
        if (n<0) { if (errno==EINTR) continue; status=3; break; }
        blake3_hasher_update(&h, buf, (size_t)n);
        offset += n;
    }
    free(buf);
    if (status) return status;
    if (fstat(fd,&after) || before.st_ino!=after.st_ino || before.st_dev!=after.st_dev ||
        before.st_size!=offset || after.st_size!=offset || before.st_mode!=after.st_mode ||
        before.st_nlink!=after.st_nlink || before.st_mtim.tv_sec!=after.st_mtim.tv_sec ||
        before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec || before.st_ctim.tv_sec!=after.st_ctim.tv_sec ||
        before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec) return 4;
    blake3_hasher_finalize(&h,out,BLAKE3_OUT_LEN);
    *length=(uint64_t)offset;
    return 0;
}
