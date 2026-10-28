#define _GNU_SOURCE
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
__attribute__((constructor))
static void capture_tool(void) {
    const char *out=getenv("OHM_PRIVATE_CG_OUT"),*select=getenv("OHM_PRIVATE_CG_TOOL"),*tools=getenv("OHM_PRIVATE_CG_ROOT");
    if(!out || !select || !tools)return;
    char path[PATH_MAX]; ssize_t nn=readlink("/proc/self/exe",path,sizeof(path)-1);
    if(nn<=0)return;
    path[nn]=0; const char *tool=strrchr(path,'/');if(!tool || strcmp(tool+1,select))return;
    char *s=malloc(2097152);if(!s)_exit(226);
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC);if(fd<0)_exit(227);
    ssize_t n=0,k;
    while(n<2097151 && (k=read(fd,s+n,2097151-n))>0)n+=k;
    close(fd); if(n<=0||n==2097151||s[n-1])_exit(228);
    char *param=strchr(s,0)+1;
    if(param<s+n && param[0]=='+')return;
    int ac=0;for(ssize_t i=0;i<n;++i)if(!s[i])++ac;
    char exe[PATH_MAX],lib[PATH_MAX],output[PATH_MAX],log[PATH_MAX],ar[PATH_MAX];
    if(snprintf(exe,sizeof(exe),"%s/usr/bin/valgrind.bin",tools)>=(int)sizeof(exe) ||
       snprintf(lib,sizeof(lib),"%s/usr/libexec/valgrind",tools)>=(int)sizeof(lib) ||
       snprintf(output,sizeof(output),"--callgrind-out-file=%s/callgrind.%%p",out)>=(int)sizeof(output) ||
       snprintf(log,sizeof(log),"--log-file=%s/valgrind.%%p",out)>=(int)sizeof(log) ||
       snprintf(ar,sizeof(ar),"%s/%ld-%s.args",out,(long)getpid(),select)>=(int)sizeof(ar))_exit(229);
    fd=open(ar,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0||write(fd,s,n)!=n||close(fd))_exit(230);
    char **av=calloc((size_t)ac+12,sizeof(char*));if(!av)_exit(231);
    int a=0;av[a++]=exe;av[a++]="--tool=callgrind";av[a++]="--trace-children=no";
    av[a++]="--collect-jumps=no";av[a++]=output;av[a++]=log;av[a++]=path;
    for(char *v=param;v<s+n;v=strchr(v,0)+1)av[a++]=v;
    av[a]=NULL;
    unsetenv("LD_PRELOAD");unsetenv("OHM_PRIVATE_CG_OUT");unsetenv("OHM_PRIVATE_CG_TOOL");unsetenv("OHM_PRIVATE_CG_ROOT");
    if(setenv("VALGRIND_LIB",lib,1))_exit(232);
    execv(exe,av);_exit(233);
}
