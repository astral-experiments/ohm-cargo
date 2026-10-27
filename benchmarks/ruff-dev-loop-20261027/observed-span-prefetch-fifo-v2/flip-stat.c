#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <execinfo.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <linux/stat.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
static _Atomic int flipped,regular,seen;
static int watched(const char *path) {
    const char *expected=getenv("OBS_FIFO_PATH"),*image=getenv("OBS_FIFO_CARGO");
    if (!path || !expected || !image || strcmp(path,expected)) return 0;
    char exe[4096];long n=syscall(SYS_readlinkat,AT_FDCWD,"/proc/self/exe",exe,sizeof(exe)-1);
    if(n<1)return 0;
    exe[n]=0;return strcmp(exe,image)==0;
}
static void event(const char *what,int status,int flags) {
    const char *log=getenv("OBS_FIFO_LOG");if(!log)return;
    int fd=syscall(SYS_openat,AT_FDCWD,log,O_WRONLY|O_APPEND|O_CLOEXEC,0);if (fd<0)return;
    char buf[256];int n=snprintf(buf,sizeof(buf),"%s pid=%d status=%d flags=%#x\n",what,getpid(),status,flags);
    syscall(SYS_write,fd,buf,n);
    if(!strcmp(what,"switch")) {void *frames[25];int nf=backtrace(frames,25);backtrace_symbols_fd(frames,nf,fd);}
    syscall(SYS_close,fd);
}
int statx(int fd,const char *name,int flags,unsigned int mask,struct statx *s) {
    static int (*real)(int,const char*,int,unsigned int,struct statx*);
    if(!real)real=dlsym(RTLD_NEXT,"statx");
    int result=real(fd,name,flags,mask,s);int saved=errno;
    if(watched(name) && result==0 && S_ISREG(s->stx_mode)) {atomic_store(&regular,1);event("regular-stat",s->stx_size,flags);
        if (getenv("OBS_FIFO_AT_STAT") && atomic_fetch_add(&seen,1)==1 && !atomic_exchange(&flipped,1)) {
            const char *fifo=getenv("OBS_FIFO_READY");
            if (fifo && syscall(SYS_renameat2,AT_FDCWD,name,AT_FDCWD,fifo,RENAME_EXCHANGE)==0) event("switch", 0, flags);
        }}
    errno=saved;return result;
}
static void before(const char *p,int flags) {
    if(!watched(p))return;
    event("opening",atomic_load(&regular),flags);
    if(getenv("OBS_FIFO_AT_STAT") || !atomic_load(&regular) || atomic_exchange(&flipped,1))return;
    const char *swap=getenv("OBS_FIFO_READY");if(!swap)return;
    if(syscall(SYS_renameat2,AT_FDCWD,p,AT_FDCWD,swap,RENAME_EXCHANGE)!=0) {event("exchange-failure",errno,flags);return;}
    event("switch",0,flags);
}
#define OPEN(fn) \
int fn(const char *p,int flags,...) { \
 static int (*real)(const char*,int,...);if(!real)real=dlsym(RTLD_NEXT,#fn); \
 mode_t mode=0;if((flags&O_CREAT)||((flags&O_TMPFILE)==O_TMPFILE)){va_list ap;va_start(ap,flags);mode=va_arg(ap,int);va_end(ap);} \
 before(p,flags);return real(p,flags,mode); \
}
#define OPENAT(fn) \
int fn(int fd,const char *p,int flags,...) { \
 static int (*real)(int,const char*,int,...);if(!real)real=dlsym(RTLD_NEXT,#fn); \
 mode_t mode=0;if((flags&O_CREAT)||((flags&O_TMPFILE)==O_TMPFILE)){va_list ap;va_start(ap,flags);mode=va_arg(ap,int);va_end(ap);} \
 before(p,flags);return real(fd,p,flags,mode); \
}
OPEN(open)
OPEN(open64)
OPENAT(openat)
OPENAT(openat64)
