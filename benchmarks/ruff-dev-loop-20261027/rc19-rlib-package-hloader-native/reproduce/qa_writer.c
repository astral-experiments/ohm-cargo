#define _GNU_SOURCE
#include <signal.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <string.h>
#include <unistd.h>

static volatile sig_atomic_t count=0;
static void sigsize(int n){(void)n;count++;}
int main(int argc,char **argv){
    (void)argc;(void)argv;
    char *data=getenv("QA_INPUT"),*tmp=getenv("QA_TMP"),*final=getenv("QA_FINAL"),*limit=getenv("QA_LIMIT");
    int r=open(data,O_RDONLY|O_CLOEXEC);if(r<0)return 2;
    struct stat s;if(fstat(r,&s)||s.st_size<=0)return 3;
    char *source=mmap(NULL,s.st_size,PROT_READ,MAP_SHARED,r,0);if(source==MAP_FAILED)return 4;
    if(limit){struct rlimit v; if(getrlimit(RLIMIT_FSIZE,&v))return 23;
        v.rlim_cur=(rlim_t)strtoull(limit,NULL,10);if(setrlimit(RLIMIT_FSIZE,&v))return 24;
        if(signal(SIGXFSZ,sigsize)==SIG_ERR)return 25;
    }
    int fd=open(tmp,O_RDWR|O_CLOEXEC|O_CREAT|O_EXCL,0666);if(fd<0)return 6;
    errno=0;ssize_t first=write(fd,source,(size_t)s.st_size);int e1=first>=0?0:errno;
    ssize_t second=0;int e2=0;
    if(first>=0&&first<s.st_size){errno=0;second=write(fd,source+first,(size_t)(s.st_size-first));e2=second>=0?0:errno;}
    int c=close(fd);int pub=rename(tmp,final);printf("%zd %d %zd %d %d %d %d\n",first,e1,second,e2,(int)count,c,pub);
    munmap(source,(size_t)s.st_size);close(r);return c||pub?11:0;
}
