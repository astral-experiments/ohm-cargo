#define _GNU_SOURCE
#include <sys/inotify.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <poll.h>
#include <time.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
static void record(int d,const char *key){
    int fd=openat(d,key,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
    if(fd<0||write(fd,"1",1)!=1||close(fd))_exit(91);
}
static int64_t ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
int main(void){
    const char *dir=getenv("CONDITIONAL_PIPELINE_CONTROL"), *expected=getenv("EVIDENCE_EXPECT");
    if(!dir||!expected||(strcmp(expected,"parent-started")&&strcmp(expected,"middle-started")))return 90;
    int d=open(dir,O_RDONLY|O_DIRECTORY|O_CLOEXEC),f=inotify_init1(IN_CLOEXEC|IN_NONBLOCK);
    if(d<0||f<0||inotify_add_watch(f,dir,IN_CLOSE_WRITE|IN_MOVED_TO)<0)return 92;
    record(d,"qa-notification-delivered");
    const int64_t deadline=ms()+3000;struct stat st;char events[2048];
    while(fstatat(d,expected,&st,0)<0||!st.st_size){
        long rem=deadline-ms();if(rem<=0){record(d,"qa-handshake-timeout");return 93;}
        struct pollfd p={f,POLLIN,0};int n=poll(&p,1,(int)rem);
        if(n<0&&errno==EINTR)continue;
        if(n<0)return 94;
        if(n>0){while(read(f,events,sizeof(events))>0){}}
    }
    record(d,"qa-consumer-observed");return 0;
}
