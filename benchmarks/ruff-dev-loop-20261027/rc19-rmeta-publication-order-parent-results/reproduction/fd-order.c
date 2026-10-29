#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static int role(const char *path) {
    if (!path) return 0;
    const char *p = strrchr(path, '/'); p = p ? p + 1 : path;
    size_t n = strlen(p);
    if (n <= 7 || strcmp(p + n - 6, ".rmeta")) return 0;
    if (!strncmp(p, "libprovider-", 12)) return 1;
    if (!strncmp(p, "libreader-", 10)) return 2;
    return 0;
}
static long long ns(struct timespec t) {
    return (long long)t.tv_sec * 1000000000LL + t.tv_nsec;
}
static int original_cargo(void) {
    const char *origin = getenv("WITNESS_ORIGINAL_CARGO"); struct stat image, self;
    return origin && !stat(origin, &image) && !stat("/proc/self/exe", &self)
        && self.st_dev == image.st_dev && self.st_ino == image.st_ino;
}
static void log_entry(const char *dir, const char *action, int unit, int restore, const char *path, const struct timespec times[2]) {
    char fn[PATH_MAX], msg[PATH_MAX + 350];
    snprintf(fn, sizeof fn, "%s/control.tsv", dir);
    int fd = open(fn, O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC, 0600); if (fd < 0) _exit(85);
    struct stat st;
    long long previous = stat(path, &st) ? -1 : ns(st.st_mtim);
    int n = snprintf(msg, sizeof msg, "%s\t%ld\t%ld\t%d\t%d\t%lld\t%lld\t%s\n",
        action, (long)getpid(), (long)syscall(SYS_gettid), unit, restore, previous,
        times ? ns(times[1]) : -1, path);
    if (n < 0 || n >= sizeof msg || write(fd, msg, n) != n) _exit(86);
    close(fd);
}
static void finished(const char *dir, int unit) {
    char path[PATH_MAX]; snprintf(path, sizeof path, "%s/done-%d", dir, unit);
    int fd = open(path, O_WRONLY|O_CREAT|O_CLOEXEC, 0600); if (fd < 0) _exit(87); close(fd);
}
static int wait_on(const char *dir, int other) {
    char path[PATH_MAX]; snprintf(path, sizeof path, "%s/done-%d", dir, other);
    for (int i=0;i<4500;i++) {
        if (!access(path, F_OK)) return 0;
        struct timespec t={0,2000000}; nanosleep(&t,NULL);
    }
    return -1;
}
int utimensat(int fd, const char *path, const struct timespec times[2], int flags) {
    static int (*real_call)(int,const char *,const struct timespec[2],int);
    if (!real_call) real_call=dlsym(RTLD_NEXT, "utimensat");
    int unit=role(path); const char *dir=getenv("WITNESS_EVENTS"), *order=getenv("WITNESS_ORDER");
    if (!dir || !unit || !original_cargo()) return real_call(fd,path,times,flags);
    int saved=errno, restore= times && times[0].tv_nsec==UTIME_OMIT;
    log_entry(dir,"before",unit,restore,path,times);
    if (!restore && order && ((!strcmp(order,"provider-late") && unit==1) || (!strcmp(order,"provider-first") && unit==2))) {
        log_entry(dir,"hold",unit,restore,path,times);
        int timeout=wait_on(dir,3-unit);
        log_entry(dir,timeout?"timeout":"release",unit,restore,path,times);
    }
    errno=saved;
    int rc=real_call(fd,path,times,flags); saved=errno;
    log_entry(dir,rc?"error":"after",unit,restore,path,times);
    if (!rc && restore) finished(dir,unit);
    errno=saved;return rc;
}

int futimens(int fd,const struct timespec times[2]) {
    static int (*real_call)(int,const struct timespec[2]);
    if (!real_call) real_call=dlsym(RTLD_NEXT,"futimens");
    char fdpath[80],name[PATH_MAX];snprintf(fdpath,sizeof fdpath,"/proc/self/fd/%d",fd);
    ssize_t n=readlink(fdpath,name,sizeof name-1);if(n<0 || n>=sizeof name-1)return real_call(fd,times);name[n]=0;
    int unit=role(name); const char *dir=getenv("WITNESS_EVENTS"), *order=getenv("WITNESS_ORDER");
    if(!unit||!dir||!original_cargo())return real_call(fd,times);
    int saved=errno,restore=times&&times[0].tv_nsec==UTIME_OMIT;
    log_entry(dir,"before-fd",unit,restore,name,times);
    if(!restore&&order&&((!strcmp(order,"provider-late")&&unit==1)||(!strcmp(order,"provider-first")&&unit==2))) {
        log_entry(dir,"hold-fd",unit,restore,name,times);
        int timeout=wait_on(dir,3-unit);
        log_entry(dir,timeout?"timeout-fd":"release-fd",unit,restore,name,times);
    }
    errno=saved;
    int rc=real_call(fd,times);saved=errno;
    log_entry(dir,rc?"error-fd":"after-fd",unit,restore,name,times);
    if(!rc&&restore)finished(dir,unit);
    errno=saved;return rc;
}
