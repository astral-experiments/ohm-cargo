#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <time.h>

struct cost { uint64_t constructs, destroys, constructor_ns, destructor_ns; };
static _Thread_local struct cost measured;
static _Thread_local int active;

static uint64_t now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

void context_measure_begin(void) { measured = (struct cost){0}; active = 1; }
void context_measure_end(struct cost *out) { active = 0; *out = measured; }

void _ZN4llvm11LLVMContextC1Ev(void *self) {
    static void (*original)(void *);
    if (!original) { original = dlsym(RTLD_NEXT, "_ZN4llvm11LLVMContextC1Ev"); assert(original); }
    if (!active) { original(self); return; }
    uint64_t start = now();
    original(self);
    measured.constructor_ns += now() - start;
    measured.constructs++;
}

void _ZN4llvm11LLVMContextD1Ev(void *self) {
    static void (*original)(void *);
    if (!original) { original = dlsym(RTLD_NEXT, "_ZN4llvm11LLVMContextD1Ev"); assert(original); }
    if (!active) { original(self); return; }
    uint64_t start = now();
    original(self);
    measured.destructor_ns += now() - start;
    measured.destroys++;
}
