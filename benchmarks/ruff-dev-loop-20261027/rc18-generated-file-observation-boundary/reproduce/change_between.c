#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>
static _Atomic unsigned opens;
static void observe(const char *path) {
    const char *watched=getenv("CARGO_PREP_WATCHED");
    if (!watched || strcmp(path,watched)!=0) return;
    char exe[4096]; ssize_t len=readlink("/proc/self/exe",exe,sizeof(exe)-1);
    if (len<=0) return;
    exe[len]=0;
    const char *base=strrchr(exe,'/'); if (!base || strcmp(base+1,"cargo")) return;
    unsigned n=atomic_fetch_add(&opens,1)+1;
    const char *replace=getenv("CARGO_PREP_REPLACEMENT");
    if (n==2 && replace && *replace && rename(replace,path)!=0) _exit(109);
    const char *log=getenv("CARGO_PREP_LOG");
    int fd=syscall(SYS_openat,AT_FDCWD,log,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0600);
    if(fd<0) _exit(110);
    char line[100];int count=snprintf(line,sizeof(line),"cargo-open %u pid %d mutated %d\n", n,getpid(),n==2 && replace && *replace);
    if(syscall(SYS_write,fd,line,count)!=count) _exit(111);
    syscall(SYS_close,fd);
}
#define INTERCEPT(NAME) \
int NAME(const char *path,int flags,...) { \
 int before=errno;mode_t mode=0; \
 if ((flags&O_CREAT) || (flags&O_TMPFILE)==O_TMPFILE) {va_list ap;va_start(ap,flags);mode=va_arg(ap,int);va_end(ap);} \
 int (*actual)(const char*,int,...)=dlsym(RTLD_NEXT,#NAME); \
 if (!actual) _exit(112);observe(path);errno=before;return actual(path,flags,mode); \
}
INTERCEPT(open)
INTERCEPT(open64)
