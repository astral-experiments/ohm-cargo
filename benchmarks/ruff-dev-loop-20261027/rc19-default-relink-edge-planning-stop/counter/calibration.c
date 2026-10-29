#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
static void *loop(void *input) {
    unsigned long long n=(unsigned long long)input;
    asm volatile("1: sub $1,%0; jne 1b" : "+r"(n) :: "cc");
    return 0;
}
static char *self;
static void *fork_many(void *arg) {
    const char *n=arg;
    for(int k=0;k<4;k++) {
        pid_t pid=fork();
        if(pid==0){execl(self,self,"child",n,(char *)0);_exit(7);}
        int status=0;if(pid<0 || waitpid(pid,&status,0)!=pid || status!=0)_exit(8);
    }
    return 0;
}
int main(int argc,char **argv) {
    self=argv[0];
    if(argc==3 && argv[1][0]=='m') {
        pthread_t a,b;
        if(pthread_create(&a,NULL,fork_many,argv[2]) || pthread_create(&b,NULL,fork_many,argv[2]))return 5;
        loop((void *)2000000);
        if(pthread_join(a,NULL) || pthread_join(b,NULL))return 6;
        return 0;
    }

    if (argc!=3) return 1;
    if (argv[1][0]=='c') {
        if (argv[1][1]=='h') { loop((void *)strtoull(argv[2],0,10)); return 0; }
        pid_t pid=fork();if(pid<0)return 2;
        if(!pid){execl(argv[0],argv[0],"child",argv[2],(char *)0);_exit(3);}
        int status=0;return waitpid(pid,&status,0)==pid&&status==0?0:4;
    }
    pthread_t t;
    if(pthread_create(&t,NULL,loop,(void *)strtoull(argv[2],0,10)))return 5;
    if(pthread_join(t,NULL))return 6;return 0;
}
