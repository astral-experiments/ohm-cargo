#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
__attribute__((constructor)) static void observe(void) {
  char path[4096], *name;
  ssize_t count = readlink("/proc/self/exe", path, sizeof(path)-1);
  if(count<=0 || count>=sizeof(path)-1) return;
  path[count]=0; name=strrchr(path,'/');
  if(!name || strcmp(name+1,"rustc")) return;
  unsigned char *fn=dlsym(RTLD_DEFAULT,getenv("OHM_JOIN_SYMBOL"));
  unsigned char expected[7]={0xc6,0x80,0xa6,0x1b,0,0,1};
  size_t n=7, delta=0x166;
  if(getenv("OHM_JOIN_DELTA")) {
    delta=strtoul(getenv("OHM_JOIN_DELTA"),0,0);
    const char *p=getenv("OHM_JOIN_BYTES"); unsigned a[7];
    if(!p || sscanf(p,"%02x%02x%02x%02x%02x%02x%02x",a,a+1,a+2,a+3,a+4,a+5,a+6)!=7) _exit(97);
    for(int i=0;i<7;i++) expected[i]=a[i];
  }
  if(!fn || memcmp(fn+delta,expected,n)) _exit(95);
  FILE *receipt=fopen(getenv("OHM_JOIN_RECEIPT"),"a");
  if(!receipt) _exit(98);
  fprintf(receipt,"%d %s %zx\n",getpid(),getenv("OHM_JOIN_OPERATION"),delta); fclose(receipt);
  if(strcmp(getenv("OHM_JOIN_OPERATION"),"drop")) return;
  unsigned char *p=fn+delta; size_t page=(size_t)sysconf(_SC_PAGESIZE);
  void *base=(void*)((uintptr_t)p & ~(page-1));
  if(mprotect(base,page,PROT_READ|PROT_WRITE|PROT_EXEC)) _exit(96);
  memset(p,0x90,n); __builtin___clear_cache((char*)p,(char*)p+n);
  if(mprotect(base,page,PROT_READ|PROT_EXEC)) _exit(96);
}
