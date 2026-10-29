#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

struct input {char *src, *alias; int group, fd; dev_t device; ino_t inode; off_t size;};
static void fail(const char *label){perror(label);exit(2);}
static uint64_t now(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t))fail("clock");return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;}
static void opened(struct input *p,const char *name){
    p->fd=open(name,O_RDONLY|O_CLOEXEC);if(p->fd<0)fail("open");
}
static uint64_t confirm(struct input *p){
    struct stat s;unsigned char b[16];if(fstat(p->fd,&s)||pread(p->fd,b,sizeof b,0)!=(ssize_t)sizeof b)fail("acquire");
    if(s.st_dev!=p->device||s.st_ino!=p->inode||s.st_size!=p->size||memcmp(b,"\177ELF",4))exit(3);
    if(close(p->fd))fail("close");
    return (uint64_t)s.st_size+(uint64_t)b[4]+(uint64_t)b[5];
}
int main(int argc,char **argv){
    if(argc!=3||(*argv[1]!='A'&&*argv[1]!='B'))return 2;
    FILE *list=fopen(argv[2],"r");if(!list)fail("list");
    size_t cap=8192,used=0,lc=0;struct input *a=calloc(cap,sizeof *a);char *line=NULL;
    while(getline(&line,&lc,list)>=0){
        if(used==cap)exit(3);
        line[strcspn(line,"\n")]=0;char *p=line,*g=strsep(&p,"\t"),*src=strsep(&p,"\t");if(!p)exit(3);
        struct input *o=&a[used++];o->group=atoi(g);o->src=strdup(src);o->alias=strdup(p);
        struct stat s;if(stat(src,&s)||!S_ISREG(s.st_mode))fail("source");
        o->device=s.st_dev;o->inode=s.st_ino;o->size=s.st_size;
        if(lstat(o->alias,&s)==0||errno!=ENOENT)exit(4);
    }
    if(used!=4212||ferror(list))exit(5);
    uint64_t st=now(),sum=0;int physical=*argv[1]=='A';
    for(size_t lo=0;lo<used;){
        size_t hi=lo+1;while(hi<used&&a[hi].group==a[lo].group)hi++;
        for(size_t k=lo;k<hi;k++){if(physical){if(link(a[k].src,a[k].alias))fail("link");}else{opened(&a[k],a[k].src);}}
        for(size_t k=lo;k<hi;k++){if(physical)opened(&a[k],a[k].alias);sum+=confirm(&a[k]);}
        if(physical)for(size_t k=lo;k<hi;k++){if(unlink(a[k].alias))fail("unlink");}
        lo=hi;
    }
    uint64_t elapsed=now()-st;printf("%s %zu %" PRIu64 " %" PRIu64 "\n",argv[1],used,sum,elapsed);return 0;
}
