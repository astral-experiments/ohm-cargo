#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/syscall.h>
#include <unistd.h>
int flock(int fd,int op) {
    int result = syscall(SYS_flock,fd,op);
    if(result!=0) return result;
    char link[64], path[4096];
    snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);
    ssize_t n=readlink(link,path,sizeof(path)-1);
    if(n<=0)return result;
    path[n]=0;
    if(strstr(path,"/.prune-lock")==NULL)return result;
    static int captured;
    int log=open(getenv("FORK_AUDIT"),O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC,0600);
    if(log<0)_exit(82);
    dprintf(log,"pid=%ld op=%d\n",(long)getpid(),op);
    if(!captured && op==(LOCK_EX|LOCK_NB)){
        captured=1;
        pid_t child=fork();
        if(child<0)_exit(83);
        if(child==0){dprintf(log,"child holds inherited fd\n");usleep(200000);_exit(0);}
        dprintf(log,"parent child=%ld\n",(long)child);
    }
    close(log);
    return result;
}
