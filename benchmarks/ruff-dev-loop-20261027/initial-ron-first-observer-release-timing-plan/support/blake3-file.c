#include <stdio.h>
#include "blake3.h"
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 3;
    blake3_hasher h;
    blake3_hasher_init(&h);
    unsigned char b[65536], digest[BLAKE3_OUT_LEN];
    size_t n;
    while ((n = fread(b, 1, sizeof b, f)) != 0) blake3_hasher_update(&h, b, n);
    if (ferror(f) || fclose(f)) return 4;
    blake3_hasher_finalize(&h, digest, sizeof digest);
    for (size_t i = 0; i < sizeof digest; i++) printf("%02x", digest[i]);
    puts("");
    return 0;
}
