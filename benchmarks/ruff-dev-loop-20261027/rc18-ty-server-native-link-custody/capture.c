#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void fail(const char *s) { perror(s); _exit(120); }
static void put(int fd, const char *s, size_t n) {
    while (n) { ssize_t k = write(fd,s,n); if (k<=0) fail("write"); s += k; n -= (size_t)k; }
}
static int newfile(int root,const char *name) {
    int fd=openat(root,name,O_WRONLY|O_CLOEXEC|O_NOFOLLOW|O_CREAT|O_EXCL,0600);
    if(fd<0) fail(name); return fd;
}
static void vec(int root,const char *name,char *const *v) {
    int fd=newfile(root,name); for (;*v;v++) put(fd,*v,strlen(*v)+1); if(close(fd)) fail(name);
}
static void bytes(int root,const char *name,const char *path) {
    int old=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC); if(old<0) fail(path);
    struct stat st; if(fstat(old,&st)||!S_ISREG(st.st_mode)||st.st_size>2000000) fail("non-regular/large temporary");
    int dest=newfile(root,name); char buf[8192]; ssize_t n;
    while((n=read(old,buf,sizeof buf))>0) put(dest,buf,(size_t)n);
    if(n<0||close(dest)||close(old)) fail("temp-copy");
}
int main(int argc,char **argv,char **envp) {
    int d=open(CAPTURE,O_RDONLY|O_CLOEXEC|O_DIRECTORY); if(d<0) fail("capture-dir");
    vec(d,"argv.bin",argv); vec(d,"env.bin",envp); char *pwd=getcwd(NULL,0); if(!pwd) fail("getcwd");
    int cwd=newfile(d,"cwd.bin"); put(cwd,pwd,strlen(pwd)); if(close(cwd))fail("cwd");
    cpu_set_t mask; if(sched_getaffinity(0,sizeof mask,&mask)||CPU_COUNT(&mask)!=4||!CPU_ISSET(24,&mask)||!CPU_ISSET(25,&mask)||!CPU_ISSET(26,&mask)||!CPU_ISSET(27,&mask))fail("affinity");
    size_t ns=0,nr=0,nd=0; const char *key="-plugin-opt=-fresolution=";
    for (int i=1;i<argc;i++) {
        const char *s=argv[i],*last=strrchr(s,'/');
        if(last && !strcmp(last,"/symbols.o")) { bytes(d,"symbols.o",s); ns++; }
        if(!strncmp(s,key,strlen(key))) { bytes(d,"resolution.res",s+strlen(key)); nr++; }
        if(!strncmp(s,"-L",2) && last && !strcmp(last,"/raw-dylibs")) {
            int info=newfile(d,"raw-dylibs"); DIR *dylibs=opendir(s+2);
            if (!dylibs) { if(errno!=ENOENT)fail("opendir"); put(info,"absent",6); }
            else { struct dirent *e; errno=0; while((e=readdir(dylibs))) if(strcmp(e->d_name,".")&&strcmp(e->d_name,".."))fail("nonempty raw-dylibs"); if(errno||closedir(dylibs))fail("readdir"); put(info,"empty-directory",15); }
            if(close(info))fail("raw-dylib receipt"); nd++;
        }
    }
    if(ns!=1||nr!=1||nd!=1||close(d))fail("unexpected temporary roster");
    execve(STOCK,argv,envp); fail("stock execve"); return 1;
}
