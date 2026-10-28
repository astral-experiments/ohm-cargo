#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#define NF 1024
#define BS 16384
static const char *suffixes[]={"/ruff_unicode_names2/f17900a6a44d7d41/out/generated.rs","/ruff_unicode_names2/f17900a6a44d7d41/out/generated_phf.rs","/ty_vendored/55bc40c417024a68/out/zipped_typeshed.zip"};
static const uint32_t offsets[]={1167,1788355,75306};
struct info {size_t first_request,subsequent_max,bytes,requests,issued; uint64_t start; unsigned id;};
static struct info tracked[NF];
static _Atomic int initialized;
static int mode, fdlog;
static int (*realopen)(const char*,int,...),(*realopen64)(const char*,int,...),(*realclose)(int);
static ssize_t (*realread)(int,void*,size_t);
static uint64_t now(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t))_exit(113);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
__attribute__((constructor)) static void ready(void){
 realread=dlsym(RTLD_NEXT,"read");realopen=dlsym(RTLD_NEXT,"open");realopen64=dlsym(RTLD_NEXT,"open64");realclose=dlsym(RTLD_NEXT,"close");
 if(!realread||!realopen||!realopen64||!realclose)_exit(115);
 const char *m=getenv("OHM_STREAM_MODE"),*log=getenv("OHM_STREAM_PROBE");
 if(m&&log){mode=m[0]=='B';fdlog=syscall(SYS_openat,AT_FDCWD,log,O_CREAT|O_WRONLY|O_APPEND|O_CLOEXEC,0600); if(fdlog<0)_exit(114);atomic_store(&initialized,1);}
}
static void pin(int fd,const char *path){
 if(!atomic_load(&initialized)||fd<0||fd>=NF)return;
 if(!strstr(path,"/target/debug/build/workspaces/5183fbb458952a35/v2-63fe60e05f649687/"))return;
 size_t len=strlen(path);
 for(unsigned i=0;i<3;i++){size_t suffix=strlen(suffixes[i]);if(len>=suffix&&memcmp(path+len-suffix,suffixes[i],suffix)==0){tracked[fd]=(struct info){.id=i+1,.start=now()};break;}}
}
#define WOPEN(name, real) int name(const char *p,int f,...){mode_t m=0;if((f&O_CREAT)||(f&O_TMPFILE)==O_TMPFILE){va_list a;va_start(a,f);m=va_arg(a,int);va_end(a);}int fd=real?real(p,f,m):syscall(SYS_openat,AT_FDCWD,p,f,m);pin(fd,p);return fd;}
WOPEN(open,realopen)
WOPEN(open64,realopen64)
ssize_t read(int fd,void *buf,size_t count){
 if((unsigned)fd<NF&&tracked[fd].id){struct info *t=&tracked[fd];if(!t->requests){t->first_request=count;if(mode&&count==BS)count=BS-(offsets[t->id-1]%BS);t->issued=count;}else if(count>t->subsequent_max)t->subsequent_max=count;
  ssize_t n=realread(fd,buf,count);if(n>=0){t->requests++;t->bytes+=(size_t)n;}return n;}
 return realread?realread(fd,buf,count):syscall(SYS_read,fd,buf,count);
}
int close(int fd){
 if((unsigned)fd<NF&&tracked[fd].id){struct info t=tracked[fd];tracked[fd].id=0;uint64_t dur=now()-t.start;char line[256];
 int n=snprintf(line,sizeof(line),"%u %zu %zu %zu %zu %zu %"PRIu64"\n",t.id,t.first_request,t.issued,t.subsequent_max,t.requests,t.bytes,dur);if(syscall(SYS_write,fdlog,line,n)!=n)_exit(116);}
 return realclose?realclose(fd):syscall(SYS_close,fd);
}
