#define _GNU_SOURCE
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <limits.h>
__attribute__((constructor))
static void dispatch(int argc, char **argv) {
    char path[PATH_MAX];
    ssize_t n=readlink("/proc/self/exe",path,sizeof path-1);
    if(n<0||n>=sizeof path-1)return;
    path[n]=0;
    if(!strstr(path,"/wild-ld/ld.bfd") || argc<2 || !getenv("OHM_DEDENT_PILOT_ROOT"))return;
    char *target=getenv("OHM_DEDENT_DIAGNOSTIC_WILD");
    if(!target || target[0]!='/')return;
    execv(target,argv);_exit(125);
}
