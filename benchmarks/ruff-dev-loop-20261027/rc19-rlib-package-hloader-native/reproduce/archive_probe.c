/* Native experiment for the released x86-64 GNU rlib writer. */
#define _GNU_SOURCE
#define _LARGEFILE64_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <limits.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>

#define NEXT(name) ((__typeof__(&name))dlsym(RTLD_NEXT,#name))
#define RESOLVE(name) next_##name=NEXT(name)
static __typeof__(&open) next_open;
static __typeof__(&open64) next_open64;
static __typeof__(&openat) next_openat;
static __typeof__(&openat64) next_openat64;
static __typeof__(&write) next_write;
static __typeof__(&close) next_close;
static __typeof__(&lseek) next_lseek;
static __typeof__(&lseek64) next_lseek64;
static __typeof__(&ftruncate) next_ftruncate;
static __typeof__(&ftruncate64) next_ftruncate64;
static __typeof__(&pwrite) next_pwrite;
static __typeof__(&pwrite64) next_pwrite64;
static __typeof__(&writev) next_writev;
static __typeof__(&rename) next_rename;
static __typeof__(&renameat) next_renameat;
static __typeof__(&renameat2) next_renameat2;
static __typeof__(&fsync) next_fsync;
static __typeof__(&fdatasync) next_fdatasync;
static __typeof__(&mmap) next_mmap;
static __typeof__(&mmap64) next_mmap64;
static __typeof__(&dup) next_dup;
static __typeof__(&dup2) next_dup2;
static __typeof__(&dup3) next_dup3;
static __typeof__(&fstat) next_fstat;
static __typeof__(&fstat64) next_fstat64;
static pthread_mutex_t guard=PTHREAD_MUTEX_INITIALIZER;
static _Atomic int tracked=-1;
static const char *outdir,*final_name,*prior_name,*mode,*shadow_name;
static char tmppath[PATH_MAX];
static bool enrolled,cloned,was_cloned,closed_ok;
static int report=-1,shadow=-1,prior_err,clone_err,fatal,shadow_err,publications;
static unsigned long long calls,skipped_calls,skipped_bytes,actual_bytes,generated_bytes,compare_bytes,short_reads,one_output;
static off_t position;
static const char *decision="no-writer",*alternate="none";
static unsigned char scratch[131072],acquired[131072];
static int barrier_once=0;
static const char *barrier_arrived,*barrier_release;
static bool finite_fsize(void){
    struct rlimit lim;
    return getrlimit(RLIMIT_FSIZE,&lim)!=0||lim.rlim_cur!=RLIM_INFINITY;
}
static void qa_acquired(void){
    if(!barrier_arrived||!barrier_release||barrier_once)return;
    barrier_once=1;
    int a=syscall(SYS_openat,AT_FDCWD,barrier_arrived,O_WRONLY|O_NOFOLLOW|O_CLOEXEC,0);
    if(a<0||syscall(SYS_write,a,"1",1)!=1){fatal=EIO;if(a>=0)syscall(SYS_close,a);return;}
    syscall(SYS_close,a);
    int b=syscall(SYS_openat,AT_FDCWD,barrier_release,O_RDONLY|O_NOFOLLOW|O_CLOEXEC,0);char ch;
    if(b<0||syscall(SYS_read,b,&ch,1)!=1||ch!='1')fatal=EIO;
    if(b>=0)syscall(SYS_close,b);
}
static char arguments[524288],*av[16384];

static ssize_t raw_write(int fd,const void *buf,size_t n){return syscall(SYS_write,fd,buf,n);}
static ssize_t normal_write(int fd,const void *buf,size_t n){return next_write?next_write(fd,buf,n):raw_write(fd,buf,n);}
static int raw_openat(int d,const char *path,int flags,mode_t m){return syscall(SYS_openat,d,path,flags,m);}
static int raw_close(int fd){return syscall(SYS_close,fd);}
static bool input_number(const char *n,unsigned long long *out){
    const char *s=getenv(n);if(!s||!*s)return false;
    char *end=NULL;errno=0;*out=strtoull(s,&end,10);return !errno&&end&&!*end;
}
static bool same_inode(const struct stat *a,const struct stat *b){
    return a->st_dev==b->st_dev&&a->st_ino==b->st_ino;
}
static void report_state(const char *event,int rc){
    if(report<0)return;
    struct stat channel;
    /* The optional receipt must not itself generate SIGXFSZ or consume a limited file. */
    if(finite_fsize()&&(syscall(SYS_fstat,report,&channel)||S_ISREG(channel.st_mode)))return;
    char buf[850];int n=snprintf(buf,sizeof buf,
        "{\"event\":\"%s\",\"mode\":\"%s\",\"pid\":%ld,\"decision\":\"%s\",\"alternate\":\"%s\","
        "\"found_output\":%llu,\"did_clone\":%d,\"prior_errno\":%d,\"clone_errno\":%d,"
        "\"write_calls\":%llu,\"skipped_calls\":%llu,\"compared_bytes\":%llu,\"skipped_bytes\":%llu,"
        "\"actual_bytes\":%llu,\"generated_bytes\":%llu,\"position\":%lld,\"short_reads\":%llu,"
        "\"closed\":%d,\"fatal_errno\":%d,\"reference_errno\":%d,\"publications\":%d,\"rc\":%d}\n",
        event,mode,(long)getpid(),decision,alternate,one_output,was_cloned,prior_err,clone_err,
        calls,skipped_calls,compare_bytes,skipped_bytes,actual_bytes,generated_bytes,
        (long long)position,short_reads,closed_ok,fatal,shadow_err,publications,rc);
    if(n>0&&(size_t)n<sizeof buf)(void)raw_write(report,buf,(size_t)n);
}
static bool inspect_argv(void){
    const char *rust=getenv("OHM_AR_RUSTC"),*crate=getenv("OHM_AR_CRATE");
    struct stat actual,expected;
    if(!rust||!crate||strcmp(crate,"ruff_linter")||stat("/proc/self/exe",&actual)||stat(rust,&expected)||!same_inode(&actual,&expected))return false;
    int fd=raw_openat(AT_FDCWD,"/proc/self/cmdline",O_RDONLY|O_CLOEXEC,0);if(fd<0)return false;
    size_t len=0;ssize_t n;
    while(len<sizeof arguments&&(n=syscall(SYS_read,fd,arguments+len,sizeof arguments-len))>0)len+=(size_t)n;
    raw_close(fd);
    if(!len||len==sizeof arguments||arguments[len-1])return false;
    int ac=0;
    for(size_t off=0;off<len;){
        if(ac==(int)(sizeof av/sizeof *av))return false;
        av[ac++]=arguments+off;off+=strlen(arguments+off)+1;
    }
    int saw_name=0,saw_out=0,saw_type=0,saw_emit=0,saw_extra=0;
    for(int i=1;i<ac;i++){
        if(!strcmp(av[i],"--crate-name")){if(++i==ac||strcmp(av[i],crate))return false;saw_name++;}
        else if(!strcmp(av[i],"--out-dir")){if(++i==ac||strcmp(av[i],outdir))return false;saw_out++;}
        else if(!strcmp(av[i],"--crate-type")){if(++i==ac||strcmp(av[i],"lib"))return false;saw_type++;}
        else if(!strncmp(av[i],"--emit",6)){if(strcmp(av[i],"--emit=dep-info,metadata,link"))return false;saw_emit++;}
        else if(!strncmp(av[i],"extra-filename=",15)){
            char buf[PATH_MAX];int k=snprintf(buf,sizeof buf,"%s/lib%s%s.rlib",outdir,crate,av[i]+15);
            if(i<2||strcmp(av[i-1],"-C")||k<0||(size_t)k>=sizeof buf||strcmp(buf,final_name))return false;
            saw_extra++;
        }else if(!strcmp(av[i],"-o")||!strcmp(av[i],"--test")||strstr(av[i],"save-temps")||strstr(av[i],"relink-only")||!strcmp(av[i],"link-only"))return false;
    }
    return saw_name==1&&saw_out==1&&saw_type==1&&saw_emit==1&&saw_extra==1;
}
__attribute__((constructor)) static void startup(void){
    RESOLVE(open);RESOLVE(open64);RESOLVE(openat);RESOLVE(openat64);RESOLVE(write);RESOLVE(close);
    RESOLVE(lseek);RESOLVE(lseek64);RESOLVE(ftruncate);RESOLVE(ftruncate64);RESOLVE(pwrite);RESOLVE(pwrite64);
    RESOLVE(writev);RESOLVE(rename);RESOLVE(renameat);RESOLVE(renameat2);RESOLVE(fsync);RESOLVE(fdatasync);
    RESOLVE(mmap);RESOLVE(mmap64);RESOLVE(dup);RESOLVE(dup2);RESOLVE(dup3);RESOLVE(fstat);RESOLVE(fstat64);
    mode=getenv("OHM_AR_MODE");outdir=getenv("OHM_AR_OUT");final_name=getenv("OHM_AR_FINAL");
    prior_name=getenv("OHM_AR_PRIOR");shadow_name=getenv("OHM_AR_REFERENCE");const char *log=getenv("OHM_AR_LOG");
    if(!mode||(strcmp(mode,"cow")&&strcmp(mode,"observe"))||!outdir||outdir[0]!='/'||!final_name||!prior_name||prior_name[0]!='/'||!log||!inspect_argv())return;
    unsigned long long supplied;struct stat pipe_id;
    if(input_number("OHM_AR_QA_LOG_FD",&supplied)&&supplied<=INT_MAX&&
       !syscall(SYS_fstat,(int)supplied,&pipe_id)&&S_ISFIFO(pipe_id.st_mode)){
        report=(int)syscall(SYS_fcntl,(int)supplied,F_DUPFD_CLOEXEC,3);
    }else report=raw_openat(AT_FDCWD,log,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(report<0)return;
    barrier_arrived=getenv("OHM_AR_QA_ARRIVED");barrier_release=getenv("OHM_AR_QA_RELEASE");
    enrolled=true;report_state("enrolled",0);
}
static bool exact_tmp(const char *s){
    size_t n=strlen(outdir);
    if(!s||strncmp(s,outdir,n)||strncmp(s+n,"/.tmp",5))return false;
    const char *t=s+n+5;size_t z=0;
    for(;z<6&&t[z];z++){
        unsigned char v=(unsigned char)t[z];
        if(!((v>='a'&&v<='z')||(v>='A'&&v<='Z')||(v>='0'&&v<='9')))return false;
    }
    return z==6&&!strcmp(t+z,".temp-archive/tmp.a");
}
static void after_open(int fd,int d,const char *s,int flags){
    if(!enrolled||fd<0||d!=AT_FDCWD||!exact_tmp(s))return;
    int save=errno;pthread_mutex_lock(&guard);
    if(++one_output!=1||strlen(s)>=sizeof tmppath||(flags&~(O_LARGEFILE|O_CLOEXEC))!=(O_RDWR|O_CREAT|O_EXCL)){decision="unexpected-open";goto done;}
    struct stat dst;
    if(syscall(SYS_fstat,fd,&dst)||!S_ISREG(dst.st_mode)||dst.st_size||dst.st_nlink!=1){decision="unexpected-output";goto done;}
    strcpy(tmppath,s);atomic_store(&tracked,fd);decision="observe";
    if(shadow_name&&*shadow_name){
        shadow=raw_openat(AT_FDCWD,shadow_name,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        if(shadow<0)shadow_err=errno;
    }
    if(finite_fsize()){
        decision="finite-fsize";if(shadow>=0){raw_close(shadow);shadow=-1;shadow_err=ENOTSUP;}goto done;
    }
    if(!strcmp(mode,"observe"))goto done;
    int prior=raw_openat(AT_FDCWD,prior_name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK|O_NOCTTY,0);
    if(prior<0){prior_err=errno;decision="prior-open";goto done;}
    struct stat old;
    unsigned long long dev,ino;char magic[8];
    if(syscall(SYS_fstat,prior,&old)||!S_ISREG(old.st_mode)||old.st_uid!=geteuid()||same_inode(&old,&dst)||
       !input_number("OHM_AR_PRIOR_DEV",&dev)||!input_number("OHM_AR_PRIOR_INO",&ino)||
       (unsigned long long)old.st_dev!=dev||(unsigned long long)old.st_ino!=ino){
        decision="prior-type-identity";
    }else if(syscall(SYS_pread64,prior,magic,sizeof magic,0)!=(ssize_t)sizeof magic||memcmp(magic,"!<arch>\n",8)){
        decision="prior-magic";
    }else if(syscall(SYS_ioctl,fd,FICLONE,prior)<0){
        clone_err=errno;decision="clone-failed";
        if(syscall(SYS_ftruncate,fd,0)<0)fatal=errno;
    }else{
        decision="cloned";cloned=true;was_cloned=true;
    }
    raw_close(prior);
done:
    report_state("open",0);pthread_mutex_unlock(&guard);errno=save;
}
static bool needs_mode(int f){return(f&O_CREAT)||((f&O_TMPFILE)==O_TMPFILE);}
#define OPEN_FN(name) int name(const char *p,int f,...){mode_t m=0;if(needs_mode(f)){va_list ap;va_start(ap,f);m=va_arg(ap,int);va_end(ap);}int fd=next_##name?next_##name(p,f,m):raw_openat(AT_FDCWD,p,f,m);after_open(fd,AT_FDCWD,p,f);return fd;}
#define OPENAT_FN(name) int name(int d,const char *p,int f,...){mode_t m=0;if(needs_mode(f)){va_list ap;va_start(ap,f);m=va_arg(ap,int);va_end(ap);}int fd=next_##name?next_##name(d,p,f,m):raw_openat(d,p,f,m);after_open(fd,d,p,f);return fd;}
OPEN_FN(open)
OPEN_FN(open64)
OPENAT_FN(openat)
OPENAT_FN(openat64)
static bool same_current(int fd,const char *data,size_t size){
    size_t off=0;
    while(off<size){
        size_t want=size-off;if(want>sizeof scratch)want=sizeof scratch;
        ssize_t n=syscall(SYS_pread64,fd,scratch,want,position+(off_t)off);
        if(n<0&&errno==EINTR)continue;
        if(n!=(ssize_t)want){short_reads++;return false;}
        compare_bytes+=want;
        if(memcmp(scratch,data+off,want))return false;
        off+=want;
    }
    return true;
}
static void mirror(const char *data,size_t size){
    if(shadow<0||shadow_err)return;
    size_t off=0;
    while(off<size){
        ssize_t n=syscall(SYS_pwrite64,shadow,data+off,size-off,position+(off_t)off);
        if(n<0&&errno==EINTR)continue;
        if(n<=0){shadow_err=n<0?errno:EIO;break;}
        off+=(size_t)n;
    }
}
static void materialize_locked(int,const char*);
static ssize_t capture_once(const void *src,size_t n){
    struct iovec mine={.iov_base=acquired,.iov_len=n};
    struct iovec theirs={.iov_base=(void*)src,.iov_len=n};
    return syscall(SYS_process_vm_readv,getpid(),&mine,1,&theirs,1,0);
}
ssize_t write(int fd,const void *buf,size_t length){
    if(fd<0||atomic_load(&tracked)!=fd)return normal_write(fd,buf,length);
    pthread_mutex_lock(&guard);
    if(atomic_load(&tracked)!=fd){pthread_mutex_unlock(&guard);return normal_write(fd,buf,length);}
    int previous=errno;signed long ret=-1;size_t done=0;calls++;bool all_equal=true;
    if(fatal){errno=fatal;goto finish;}
    /* Do not synthesize Linux's partial write, SIGXFSZ, or EFBIG. Give a finite
       live limit the original single syscall, including an overlapping old extent. */
    if((cloned||shadow>=0)&&finite_fsize()){
        materialize_locked(fd,"finite-fsize");
        if(shadow>=0){raw_close(shadow);shadow=-1;shadow_err=ENOTSUP;}
    }
    if((!cloned&&shadow<0)||length==0||length>(size_t)SSIZE_MAX){
        errno=previous;ret=normal_write(fd,buf,length);
        if(ret>0){actual_bytes+=(size_t)ret;generated_bytes+=(size_t)ret;position+=ret;}
        goto finish;
    }
    while(done<length){
        size_t want=length-done;if(want>sizeof acquired)want=sizeof acquired;
        ssize_t captured=capture_once((const char *)buf+done,want);
        if(captured<0&&errno==EINTR)continue;
        if(captured<=0){if(!captured)errno=EFAULT;ret=done?(ssize_t)done:-1;goto finish;}
        qa_acquired();if(fatal){errno=fatal;ret=done?(ssize_t)done:-1;goto finish;}
        ssize_t piece;
        if(cloned&&same_current(fd,(const char *)acquired,(size_t)captured)&&
                syscall(SYS_lseek,fd,(off_t)captured,SEEK_CUR)==position+captured){
            piece=captured;skipped_bytes+=(size_t)piece;errno=previous;
        }else{
            all_equal=false;
            errno=previous;piece=normal_write(fd,acquired,(size_t)captured);
            if(piece>0)actual_bytes+=(size_t)piece;
        }
        if(piece<=0){ret=done?(ssize_t)done:piece;goto finish;}
        int saved=errno;mirror((const char*)acquired,(size_t)piece);position+=piece;
        done+=(size_t)piece;generated_bytes+=(size_t)piece;errno=saved;
        if(piece<captured||(size_t)captured<want){ret=(ssize_t)done;goto finish;}
    }
    ret=(ssize_t)done;if(all_equal&&cloned)skipped_calls++;
finish:;int saved=errno;
    pthread_mutex_unlock(&guard);errno=saved;return ret;
}
static void materialize_locked(int fd,const char *why){
    if(cloned){
        if(syscall(SYS_ftruncate,fd,position)<0)fatal=errno;
        cloned=false;
    }
    alternate=why;
}
static void unusual(int fd,const char *why){
    if(fd<0||atomic_load(&tracked)!=fd)return;
    int saved=errno;pthread_mutex_lock(&guard);
    if(atomic_load(&tracked)==fd){
        materialize_locked(fd,why);
        /* Trace-based qualification refuses a stream with extra operations. The libc call
           after this point works with a normal file containing precisely the prefix. */
        if(shadow>=0){raw_close(shadow);shadow=-1;shadow_err=ENOTSUP;}
        atomic_store(&tracked,-1);
    }
    pthread_mutex_unlock(&guard);errno=saved;
}
int close(int fd){
    if(fd>=0&&atomic_load(&tracked)==fd){
        int previous=errno;pthread_mutex_lock(&guard);
        if(atomic_load(&tracked)==fd){
            if(cloned&&syscall(SYS_ftruncate,fd,position)<0)fatal=errno;
            cloned=false;
            if(shadow>=0){if(syscall(SYS_ftruncate,shadow,position)<0&&!shadow_err)shadow_err=errno;raw_close(shadow);shadow=-1;}
            atomic_store(&tracked,-1);closed_ok=!fatal;
        }
        pthread_mutex_unlock(&guard);errno=previous;
    }
    return next_close?next_close(fd):raw_close(fd);
}
#define SIMPLE_INT(name,sys) int name(int f){unusual(f,#name);return next_##name?next_##name(f):syscall(sys,f);}
SIMPLE_INT(fsync,SYS_fsync)
SIMPLE_INT(fdatasync,SYS_fdatasync)
SIMPLE_INT(dup,SYS_dup)
#define OFFSET_FN(name,type,sys) type name(int f,type n,int w){unusual(f,#name);return next_##name?next_##name(f,n,w):syscall(sys,f,n,w);}
OFFSET_FN(lseek,off_t,SYS_lseek)
OFFSET_FN(lseek64,off64_t,SYS_lseek)
#define TRUNC_FN(name,type) int name(int f,type n){unusual(f,#name);return next_##name?next_##name(f,n):syscall(SYS_ftruncate,f,n);}
TRUNC_FN(ftruncate,off_t)
TRUNC_FN(ftruncate64,off64_t)
#define PWRITE_FN(name,type) ssize_t name(int f,const void *p,size_t n,type o){unusual(f,#name);return next_##name?next_##name(f,p,n,o):syscall(SYS_pwrite64,f,p,n,o);}
PWRITE_FN(pwrite,off_t)
PWRITE_FN(pwrite64,off64_t)
ssize_t writev(int fd,const struct iovec *vec,int n){unusual(fd,"writev");return next_writev?next_writev(fd,vec,n):syscall(SYS_writev,fd,vec,n);}
int dup2(int a,int b){unusual(a,"dup2");unusual(b,"dup2");return next_dup2?next_dup2(a,b):syscall(SYS_dup2,a,b);}
int dup3(int a,int b,int f){unusual(a,"dup3");unusual(b,"dup3");return next_dup3?next_dup3(a,b,f):syscall(SYS_dup3,a,b,f);}
#define MAP_FN(name,type) void *name(void *a,size_t n,int p,int f,int fd,type o){unusual(fd,#name);return next_##name?next_##name(a,n,p,f,fd,o):(void *)syscall(SYS_mmap,a,n,p,f,fd,o);}
MAP_FN(mmap,off_t)
MAP_FN(mmap64,off64_t)
int fstat(int f,struct stat *p){unusual(f,"fstat");return next_fstat?next_fstat(f,p):syscall(SYS_fstat,f,p);}
int fstat64(int f,struct stat64 *p){unusual(f,"fstat64");return next_fstat64?next_fstat64(f,p):syscall(SYS_fstat,f,p);}
static bool our_rename(int a,const char *p,int b,const char *q){
    return enrolled&&a==AT_FDCWD&&b==AT_FDCWD&&tmppath[0]&&!strcmp(p,tmppath)&&!strcmp(q,final_name);
}
static int before_rename(void){
    int fd=atomic_load(&tracked);
    if(fd>=0)unusual(fd,"still-open-on-rename");
    if(fatal){errno=fatal;return -1;}
    return 0;
}
static void after_rename(int rc){int e=errno;publications++;report_state("rename",rc);errno=e;}
int rename(const char *p,const char *q){
    bool mine=our_rename(AT_FDCWD,p,AT_FDCWD,q);int rc;
    if(mine&&before_rename())rc=-1;
    else rc=next_rename?next_rename(p,q):syscall(SYS_rename,p,q);
    if(mine)after_rename(rc);
    return rc;
}
int renameat(int a,const char *p,int b,const char *q){
    bool mine=our_rename(a,p,b,q);int rc;
    if(mine&&before_rename())rc=-1;
    else rc=next_renameat?next_renameat(a,p,b,q):syscall(SYS_renameat,a,p,b,q);
    if(mine)after_rename(rc);
    return rc;
}
int renameat2(int a,const char *p,int b,const char *q,unsigned f){
    bool mine=our_rename(a,p,b,q);int rc;
    if(mine&&before_rename())rc=-1;
    else rc=next_renameat2?next_renameat2(a,p,b,q,f):syscall(SYS_renameat2,a,p,b,q,f);
    if(mine)after_rename(rc);
    return rc;
}
__attribute__((destructor)) static void finish(void){
    if(enrolled){report_state("exit",0);if(report>=0)raw_close(report);}
}
