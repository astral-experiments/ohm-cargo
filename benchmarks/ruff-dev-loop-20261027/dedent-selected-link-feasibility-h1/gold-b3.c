#include "blake3.h"
#include <stdio.h>
#include <assert.h>
int main(int argc, char** argv) {
    assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);blake3_hasher h;blake3_hasher_init(&h);
    char b[128*1024];size_t n;while((n=fread(b,1,sizeof b,f))>0)blake3_hasher_update(&h,b,n);
    assert(feof(f)&&!ferror(f));unsigned char out[32];blake3_hasher_finalize(&h,out,32);
    for(int i=0;i<32;i++)printf("%02x",out[i]);puts("");return fclose(f)!=0;
}
