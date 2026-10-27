#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <limits.h>

__attribute__((constructor))
static void capture(int argc, char **argv) {
    char self[PATH_MAX], report[PATH_MAX];
    ssize_t n = readlink("/proc/self/exe",self,sizeof self-1);
    if(n < 0 || n >= sizeof self-1) return;
    self[n] = 0;
    if(!strstr(self,"/wild-ld/ld.bfd")) return;
    const char *dir=getenv("DEDENT_WILD_ENTRY");
    if(!dir) return;
    const char *out=NULL;
    for(int i=1;i+1<argc;i++) if(strcmp(argv[i],"-o")==0) out=argv[i+1];
    if(!out) return;
    if(snprintf(report,sizeof report,"%s/%d",dir,getpid())>=sizeof report) _exit(121);
    FILE *f=fopen(report,"wx");
    if(!f) _exit(122);
    struct stat st;
    int ret=lstat(out,&st),err=ret ? errno : 0;
    fprintf(f,"%s\n%s\n%d\n",self,out,err);
    if(ret==0) fprintf(f,"%lo %llu %llu %llu %llu %ld.%09ld %ld.%09ld\n",
        (unsigned long)st.st_mode,(unsigned long long)st.st_dev,(unsigned long long)st.st_ino,
        (unsigned long long)st.st_nlink,(unsigned long long)st.st_size,
        st.st_mtim.tv_sec,st.st_mtim.tv_nsec,st.st_ctim.tv_sec,st.st_ctim.tv_nsec);
    fclose(f);
}
