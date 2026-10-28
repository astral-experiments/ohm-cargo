#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <inttypes.h>
#include <link.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

struct cost { uint64_t constructs, destroys, constructor_ns, destructor_ns; };
struct member { size_t offset, size; };
struct sink { uint64_t count, bytes; uint32_t entry; FILE *symbols; };
typedef void *(*scan_fn)(const char *, size_t, void *, void *(*)(void *, const char *), void *(*)(const char *));

static uint64_t now(void) {
    struct timespec t;
    assert(clock_gettime(CLOCK_MONOTONIC_RAW, &t) == 0);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
static void *accept(void *state, const char *name) {
    struct sink *s = state;
    size_t len = strlen(name);
    s->count++; s->bytes += len;
    if (s->symbols) {
        assert(len < UINT32_MAX);
        uint32_t size = (uint32_t)len;
        assert(fwrite(&s->entry, sizeof(s->entry), 1, s->symbols) == 1);
        assert(fwrite(&size, sizeof(size), 1, s->symbols) == 1);
        assert(fwrite(name, 1, len, s->symbols) == len);
    }
    return NULL;
}
static void *report_error(const char *e) { fprintf(stderr,"LLVM symbol lookup error: %s\n",e); return (void *)1; }

int main(int argc, char **argv) {
    assert(argc == 7);
    void *driver = dlopen(argv[1], RTLD_NOW | RTLD_GLOBAL);
    if (!driver) { fprintf(stderr,"%s\n",dlerror()); return 1; }
    struct link_map *map;
    assert(!dlinfo(driver,RTLD_DI_LINKMAP,&map));
    scan_fn scan = (scan_fn)(map->l_addr + strtoull(argv[2], NULL, 16));
    int input = open(argv[3], O_RDONLY);
    struct stat st; assert(input >= 0 && !fstat(input,&st));
    const char *data = mmap(NULL, st.st_size, PROT_READ, MAP_PRIVATE, input, 0);
    assert(data != MAP_FAILED && !memcmp(data, "!<arch>\n", 8));
    FILE *roster = fopen(argv[4],"r"); assert(roster);
    struct member members[6000]; size_t count = 0, off, size;
    while (fscanf(roster,"%zu %zu",&off,&size)==2) {
        assert(count < sizeof(members)/sizeof(*members) && off < (size_t)st.st_size && size <= (size_t)st.st_size-off);
        members[count++] = (struct member){off,size};
    }
    assert(feof(roster) && count > 0); fclose(roster);
    FILE *symbols = strcmp(argv[6],"-") ? fopen(argv[6],"wx") : NULL;
    assert(!strcmp(argv[6],"-") || symbols);
    void (*begin)(void) = dlsym(RTLD_DEFAULT,"context_measure_begin");
    void (*end)(struct cost *) = dlsym(RTLD_DEFAULT,"context_measure_end");
    int rounds = atoi(argv[5]); assert(rounds > 0 && (symbols == NULL || rounds == 1));
    for (int n=0;n<rounds;n++) {
        struct sink s = {.symbols=symbols}; struct cost cost={0};
        if (begin) begin();
        uint64_t start = now();
        for (uint32_t k=0;k<count;k++) { s.entry=k; assert(scan(data+members[k].offset,members[k].size,&s,accept,report_error)==NULL); }
        uint64_t elapsed=now()-start;
        if (end) end(&cost);
        printf("%zu %llu %llu %llu %llu %llu %llu %llu\n", count,(unsigned long long)s.count,(unsigned long long)s.bytes,(unsigned long long)elapsed,(unsigned long long)cost.constructs,(unsigned long long)cost.destroys,(unsigned long long)cost.constructor_ns,(unsigned long long)cost.destructor_ns);
    }
    if (symbols) assert(!fclose(symbols));
    assert(!munmap((void *)data,st.st_size)); close(input); return 0;
}
