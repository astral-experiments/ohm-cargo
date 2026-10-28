#define _GNU_SOURCE
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
__attribute__((constructor))
static void select_real_command(void) {
    const char *dir = getenv("OHM_DIAG_COUNT_DIR");
    const char *root = getenv("OHM_DIAG_DR_ROOT");
    if (!dir || !root) return;
    char exe[PATH_MAX]; ssize_t sz = readlink("/proc/self/exe", exe, sizeof(exe)-1);
    if(sz<=0) return;
    exe[sz]=0;
    char *base = strrchr(exe, '/'); if (!base) return; ++base;
    if (strcmp(base,"cargo") && strcmp(base,"rustc") && strcmp(base,"build_script_build") && strcmp(base,"toy")) return;
    const char *sel=getenv("OHM_DIAG_SELECT");
    if(sel && !strcmp(sel,"children") && !strcmp(base,"cargo"))return;
    if(sel && !strcmp(sel,"cargo") && strcmp(base,"cargo"))return;
    char pid[30]; snprintf(pid,sizeof(pid),"%ld",(long)getpid());
    const char *installed=getenv("OHM_DIAG_INSTRUMENTED_PID");
    if (installed && !strcmp(installed,pid)) return;
    int fd=open("/proc/self/cmdline",O_RDONLY|O_CLOEXEC); if(fd<0)_exit(211);
    char *line=malloc(2097152); if(!line)_exit(212);
    ssize_t n=0, k;
    while(n<2097151 && (k=read(fd,line+n,2097151-n))>0)n+=k;
    close(fd); if(n<=0 || n==2097151 || line[n-1])_exit(213);
    int ac=0;for(ssize_t i=0;i<n;i++)if(!line[i])ac++;
    char **arg=calloc((size_t)ac+12,sizeof(char*)); if(!arg)_exit(214);
    char *first=strchr(line,0)+1;
    if ((!strcmp(base,"cargo") || !strcmp(base,"rustc")) && first<line+n && first[0]=='+') return;
    if (!strcmp(base,"rustc") && (first>=line+n || !strncmp(first,"--print",7) || !strcmp(first,"-vV"))) return;
    char run[PATH_MAX],module[PATH_MAX],cnt[PATH_MAX];
    if(snprintf(run,sizeof(run),"%s/sdk/bin64/drrun",root)>=(int)sizeof(run) || snprintf(module,sizeof(module),"%s/client/libpidcounter.so",root)>=(int)sizeof(module) || snprintf(cnt,sizeof(cnt),"%s/%s-%s.count",dir,pid,base)>=(int)sizeof(cnt))_exit(215);
    char args_path[PATH_MAX];
    if(snprintf(args_path,sizeof(args_path),"%s/%s-%s.args",dir,pid,base)>=(int)sizeof(args_path))_exit(218);
    int out=open(args_path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(out<0 || write(out,line,(size_t)n)!=n || close(out))_exit(219);
    int a=0;arg[a++]=run;arg[a++]="-quiet";arg[a++]="-no_follow_children";arg[a++]="-c";arg[a++]=module;arg[a++]=cnt;arg[a++]="--";arg[a++]=exe;
    for(char *s=first;s<line+n;s=strchr(s,0)+1)arg[a++]=s;
    arg[a]=NULL;
    if(setenv("OHM_DIAG_INSTRUMENTED_PID",pid,1))_exit(216);
    execv(run,arg); _exit(217);
}
