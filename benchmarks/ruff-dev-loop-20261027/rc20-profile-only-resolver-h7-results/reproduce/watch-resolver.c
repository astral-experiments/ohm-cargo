#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <unistd.h>

static void fail(const char *s) { perror(s); exit(91); }
static long trace(int op,pid_t t, unsigned long off,unsigned long word) {
    errno=0; long r=ptrace(op,t,(void*)off,(void*)word);
    if(r==-1 && errno) fail("ptrace");
    return r;
}
static void debug(pid_t t,unsigned i,unsigned long v) {
    trace(PTRACE_POKEUSER,t,offsetof(struct user,u_debugreg[0])+i*sizeof(unsigned long),v);
}
static unsigned long image(pid_t t,ino_t ino) {
    char n[64],s[PATH_MAX+100]; snprintf(n,sizeof(n),"/proc/%d/maps",t);
    FILE *m=fopen(n,"r"); if(!m)fail("maps");
    unsigned long a,b,offset,i;char perm[8];
    while(fgets(s,sizeof s,m)) {
        if(sscanf(s,"%lx-%lx %7s %lx %*x:%*x %lu",&a,&b,perm,&offset,&i)==5 && !offset && i==ino){fclose(m);return a;}
    }
    fail("no matching ELF base");return 0;
}
static int group(pid_t t) {
    char n[64],s[256];int g=0;snprintf(n,sizeof n,"/proc/%d/status",t);
    FILE*f=fopen(n,"r");if(!f)return 0;
    while(fgets(s,sizeof s,f))if(sscanf(s,"Tgid: %d",&g)==1)break;
    fclose(f);return g;
}
int main(int argc,char**argv){
    if(argc<9)return 64;
    struct stat target;if(stat(argv[1],&target))fail("Cargo subject");
    FILE*f=fopen(argv[2],"wx");if(!f)fail("ledger");setlinebuf(f);
    unsigned long pc[4],base=0;for(unsigned i=0;i<4;i++)pc[i]=strtoul(argv[3+i],NULL,16);
    if(strcmp(argv[7],"--"))return 65;
    pid_t root=fork(),owner=0;int status,ret=-1;if(root<0)fail("fork");
    if(!root){trace(PTRACE_TRACEME,0,0,0);raise(SIGSTOP);execvp(argv[8],argv+8);_exit(127);}
    if(waitpid(root,&status,0)!=root || !WIFSTOPPED(status))fail("wait root");
    trace(PTRACE_SETOPTIONS,root,0,PTRACE_O_EXITKILL|PTRACE_O_TRACEEXEC|PTRACE_O_TRACECLONE|PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK);
    trace(PTRACE_CONT,root,0,0);
    while(1){
        pid_t t=waitpid(-1,&status,__WALL);if(t<0){if(errno==EINTR)continue;if(errno==ECHILD)break;fail("wait");}
        if(WIFEXITED(status)||WIFSIGNALED(status)){int rc=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);fprintf(f,"exit %d %d\n",t,rc);if(t==root)ret=rc;continue;}
        if(!WIFSTOPPED(status))fail("unexpected wait status");
        int ev=(unsigned)status>>16,sig=WSTOPSIG(status),send=0;
        if(ev==PTRACE_EVENT_EXEC){
            char n[64],exe[PATH_MAX];struct stat s;snprintf(n,sizeof n,"/proc/%d/exe",t);
            ssize_t z=readlink(n,exe,sizeof(exe)-1);if(z<0||stat(n,&s))fail("exec");exe[z]=0;
            fprintf(f,"exec %d %lu %lu %s\n",t,(unsigned long)s.st_dev,(unsigned long)s.st_ino,exe);
            if(s.st_dev==target.st_dev&&s.st_ino==target.st_ino){if(owner)fail("two Cargo processes");owner=t;base=image(t,s.st_ino);fprintf(f,"owner %d %lx\n",t,base);}
            if(t==owner){for(unsigned i=0;i<4;i++)debug(t,i,base+pc[i]);debug(t,6,0);debug(t,7,0x55);}
        }else if(ev){ /* forked TIDs report their own SIGSTOP below */ }
        else if(sig==SIGSTOP && owner){
            if(group(t)==owner){for(unsigned i=0;i<4;i++)debug(t,i,base+pc[i]);debug(t,6,0);debug(t,7,0x55);}
            else debug(t,7,0);
        }else if(sig==SIGTRAP && owner && group(t)==owner){
            struct user_regs_struct r;trace(PTRACE_GETREGS,t,0,(unsigned long)&r);
            int k=-1;for(unsigned i=0;i<4;i++)if(r.rip==base+pc[i])k=(int)i;
            if(k<0)fail("unexpected Cargo trap");
            unsigned long retpc=(unsigned long)trace(PTRACE_PEEKDATA,t,r.rsp,0);
            fprintf(f,"site %d %d %lx %lx\n",t,k,(unsigned long)r.rip-base,retpc-base);
        }else if(sig!=SIGSTOP && sig!=SIGTRAP)send=sig;
        trace(PTRACE_CONT,t,0,send);
    }
    fprintf(f,"done %d %d\n",owner,ret);fclose(f);return owner?ret:92;
}
