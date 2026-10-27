/* Exploratory lower bound. No decision to reuse is made here; this program only verifies
   selected content and exercises a full authenticated copy on regular owned tmpfs outputs. */
#define _GNU_SOURCE
#include "blake3.h"
#include <assert.h>
#include <fcntl.h>
#include <limits.h>
#include <omp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
typedef struct { char *path; const uint8_t *data; size_t len; } File;
typedef struct { const uint8_t *data; size_t len; uint8_t out[32]; } Row;
static File files[2000]; static Row rows[4000];
static uint64_t now(void) { struct timespec t; assert(!clock_gettime(CLOCK_MONOTONIC, &t)); return t.tv_sec*1000000000ULL+t.tv_nsec; }
static File *mapped(char *s, size_t *nf) {
    for(size_t j=0;j<*nf;j++) if(!strcmp(files[j].path,s)) return &files[j];
    int fd=open(s,O_RDONLY|O_CLOEXEC);
    struct stat st; assert(fd>=0 && !fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_size>0);
    uint8_t *mem=mmap(NULL,st.st_size,PROT_READ,MAP_PRIVATE,fd,0); assert(mem!=MAP_FAILED); close(fd);
    assert(*nf<2000); File *f=&files[(*nf)++]; *f=(File){strdup(s),mem,st.st_size}; return f;
}
int main(int argc,char **argv) {
    assert(argc==6); int threads=atoi(argv[1]); int repeat=atoi(argv[5]); assert(threads>0 && repeat>0); omp_set_dynamic(0); omp_set_num_threads(threads);
    FILE *m=fopen(argv[2],"r"); assert(m);size_t lo,len,n=0,nf=0,total=0;
    char path[PATH_MAX];while(fscanf(m,"%zu %zu %4095s",&lo,&len,path)==3) {
        File *f=mapped(path,&nf); assert(lo<=f->len && len<=f->len-lo); total+=len;
        /* 512 KiB domain-separated Merkle leaves remove artificial one-big-object skew. */
        size_t hi=lo+len;
        for(size_t k=lo;k<hi;k+=512*1024) { assert(n<4000);rows[n].data=f->data+k; rows[n++].len=hi-k<512*1024?hi-k:512*1024; }
    } fclose(m);assert(n>0);File *blob=mapped(argv[3],&nf);uint8_t initial[32],final[32];const size_t chunksz=512*1024;
    for(int pass=0;pass<repeat;pass++){
        uint64_t start=now();
        #pragma omp parallel for schedule(dynamic,1)
        for(size_t i=0;i<n;i++){blake3_hasher h; blake3_hasher_init(&h);blake3_hasher_update(&h,rows[i].data,rows[i].len);blake3_hasher_finalize(&h,rows[i].out,32);}
        blake3_hasher h;blake3_hasher_init(&h);
        for(size_t i=0;i<n;i++){blake3_hasher_update(&h,&rows[i].len,sizeof rows[i].len);blake3_hasher_update(&h,rows[i].out,32);}blake3_hasher_finalize(&h,final,32);
        if(!pass)memcpy(initial,final,32);else assert(!memcmp(initial,final,32));
        uint64_t hash_done=now(); int fd=open(argv[4],O_RDWR|O_TRUNC|O_CREAT|O_CLOEXEC,0775);assert(fd>=0 && !ftruncate(fd,blob->len));
        uint8_t *out=mmap(NULL,blob->len,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);assert(out!=MAP_FAILED);
        #pragma omp parallel for schedule(static)
        for(size_t i=0;i<(blob->len+chunksz-1)/chunksz;i++){size_t k=i*chunksz,z=(blob->len-k<chunksz)?blob->len-k:chunksz;memcpy(out+k,blob->data+k,z);}
        assert(!msync(out,blob->len,MS_SYNC));assert(!munmap(out,blob->len));assert(!close(fd));uint64_t end=now();
        printf("%d %d %zu %zu %zu %llu %llu ",threads,pass,n,total,blob->len,(unsigned long long)(hash_done-start),(unsigned long long)(end-hash_done));
        for(int j=0;j<32;j++)printf("%02x",final[j]);puts("");
    }
}
