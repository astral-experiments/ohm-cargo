#define _GNU_SOURCE
#include <sys/ptrace.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
#include <fcntl.h>
#include <limits.h>

/* Child-only x86 execution-register observer. No host-wide probes or patched text. */
#define CHECK(v) do{if(!(v)){fprintf(stderr,"observer %s line %d errno %d\n",#v,__LINE__,errno);exit(125);}}while(0)
static pid_t root;
static char *lockpath,*elf,*output,*actor;
static ino_t ino;static dev_t dev;
static unsigned long base;
static FILE *ledger;
static unsigned serial,seq,swapped;
static unsigned long loc[4]={0xa79e90,0x9fbe50,0xa7b5a8,0xa6e1f0};
static char const *labels[4]={"serialize_resolve","registry_loader","encoded_at_write","encoded_at_mark"};
struct state {pid_t tid;int cargo;int sys;unsigned long arg[3];unsigned long result_slot;};
static struct state ts[256]; static unsigned nt;
static int fds[8192]; /* file-descriptor table shared by Cargo threads. */
static struct state *state(pid_t t){
 for(unsigned i=0;i<nt;i++)if(ts[i].tid==t)return &ts[i];
 CHECK(nt<256);ts[nt]=(struct state){.tid=t};return &ts[nt++];
}
static long pt(enum __ptrace_request what,pid_t t,void*a,void*v){errno=0;long z=ptrace(what,t,a,v);CHECK(z!=-1||!errno);return z;}
static void addrfile(char *p,int n,pid_t t,char const *name){CHECK(snprintf(p,n,"/proc/%d/%s",t,name)<n);}
static int same_exe(pid_t t){char p[100];struct stat s;addrfile(p,sizeof(p),t,"exe");return stat(p,&s)==0&&s.st_dev==dev&&s.st_ino==ino;}
static void logexec(pid_t t){
 char f[100],ex[PATH_MAX],args[256*1024];addrfile(f,sizeof(f),t,"exe");ssize_t en=readlink(f,ex,sizeof(ex)-1);CHECK(en>0);ex[en]=0;
 addrfile(f,sizeof(f),t,"cmdline");int fd=open(f,O_RDONLY|O_CLOEXEC);CHECK(fd>=0);ssize_t z=read(fd,args,sizeof(args));close(fd);CHECK(z>=0&&z<(ssize_t)sizeof(args));char name[PATH_MAX];CHECK(snprintf(name,sizeof(name),"%s/exec-%u",output,++serial)<(int)sizeof(name));
 FILE *a=fopen(name,"wb");CHECK(a);CHECK(fwrite(args,1,z,a)==(size_t)z);fclose(a);fprintf(ledger,"%u EXEC %d %u %s\n",++seq,t,serial,ex);
}
static unsigned long image_base(pid_t t){
 char p[PATH_MAX],line[10000];addrfile(p,sizeof(p),t,"maps");FILE*f=fopen(p,"r");CHECK(f);unsigned long lo=0,hi=0,off=0,ix=0;char perm[8];
 while(fgets(line,sizeof(line),f)){if(sscanf(line,"%lx-%lx %7s %lx %*x:%*x %lu",&lo,&hi,perm,&off,&ix)==5&&ix==ino&&off==0){fclose(f);return lo;}}fclose(f);CHECK(0);return 0;
}
static void setdbg(pid_t t){for(unsigned i=0;i<4;i++)pt(PTRACE_POKEUSER,t,(void*)offsetof(struct user,u_debugreg[i]),(void*)(base+loc[i]));pt(PTRACE_POKEUSER,t,(void*)offsetof(struct user,u_debugreg[6]),NULL);pt(PTRACE_POKEUSER,t,(void*)offsetof(struct user,u_debugreg[7]),(void*)0x55);}
static int tgroup(pid_t t){char p[80],l[512];addrfile(p,sizeof(p),t,"status");FILE*f=fopen(p,"r");if(!f)return 0;int v=0;while(fgets(l,sizeof(l),f))if(sscanf(l,"Tgid: %d",&v)==1)break;fclose(f);return v;}
static unsigned capture(pid_t t,unsigned long address,size_t n){
 CHECK(n<1024*1024);unsigned char *buf=malloc(n?n:1);CHECK(buf);struct iovec l={buf,n},r={(void*)address,n};if(n)CHECK(process_vm_readv(t,&l,1,&r,1,0)==(ssize_t)n);
 char p[PATH_MAX];CHECK(snprintf(p,sizeof(p),"%s/bytes-%u",output,++serial)<(int)sizeof(p));FILE*f=fopen(p,"wb");CHECK(f);CHECK(fwrite(buf,1,n,f)==n);fclose(f);free(buf);return serial;
}
static void identfd(pid_t t,int fd,int*match,struct stat*s){
 char p[180],nm[PATH_MAX];CHECK(snprintf(p,sizeof(p),"/proc/%d/fd/%d",t,fd)<(int)sizeof(p));ssize_t z=readlink(p,nm,sizeof(nm)-1);*match=0;if(z<0)return;nm[z]=0;if(strcmp(nm,lockpath))return;CHECK(!stat(p,s));*match=1;
}
static void syscall_stop(struct state*st){
 struct __ptrace_syscall_info si;long n=pt(PTRACE_GET_SYSCALL_INFO,st->tid,(void*)sizeof(si),&si);CHECK(n>0);
 if(si.op==PTRACE_SYSCALL_INFO_ENTRY){st->sys=si.entry.nr;for(int i=0;i<3;i++)st->arg[i]=si.entry.args[i];return;}
 if(si.op!=PTRACE_SYSCALL_INFO_EXIT)return;
 long res=si.exit.rval;int nr=st->sys;unsigned long*arg=st->arg;
 if((nr==SYS_openat||nr==SYS_open||nr==SYS_openat2)&&res>=0&&res<8192){
  int found;struct stat s;identfd(st->tid,res,&found,&s);if(found){fds[res]=++serial;fprintf(ledger,"%u OPEN %d %d %ld %lu %lu %ld\n",++seq,st->tid,fds[res],res,(unsigned long)s.st_dev,(unsigned long)s.st_ino,s.st_size);}
 }else if(arg[0]<8192&&fds[arg[0]]){
  int f=fds[arg[0]];
  if(nr==SYS_read||nr==SYS_pread64){unsigned s=0;if(res>0)s=capture(st->tid,arg[1],res);fprintf(ledger,"%u READ %d %d %lu %ld %u\n",++seq,st->tid,f,arg[2],res,s);}
  else if(nr==SYS_flock)fprintf(ledger,"%u FLOCK %d %d %lu %ld\n",++seq,st->tid,f,arg[1],res);
  else if(nr==SYS_fcntl)fprintf(ledger,"%u FCNTL %d %d %lu %ld\n",++seq,st->tid,f,arg[1],res);
  else if(nr==SYS_close&&res==0){fprintf(ledger,"%u CLOSE %d %d\n",++seq,st->tid,f);fds[arg[0]]=0;}
  else if(nr==SYS_lseek)fprintf(ledger,"%u SEEK %d %d %ld\n",++seq,st->tid,f,res);
  else if(nr==SYS_mmap||nr==SYS_readv||nr==SYS_preadv){fprintf(ledger,"%u OTHER %d %d %d\n",++seq,st->tid,f,nr);}
 }
}
int main(int argc,char**argv){
 CHECK(argc>=7);elf=argv[1];lockpath=argv[2];output=argv[3];actor=argv[4];struct stat s;CHECK(!stat(elf,&s));ino=s.st_ino;dev=s.st_dev;
 char f[PATH_MAX];CHECK(snprintf(f,sizeof(f),"%s/observer",output)<(int)sizeof(f));ledger=fopen(f,"wx");CHECK(ledger);setlinebuf(ledger);
 root=fork();CHECK(root>=0);if(root==0){CHECK(ptrace(PTRACE_TRACEME,0,0,0)==0);raise(SIGSTOP);execvp(argv[5],&argv[5]);_exit(126);}
 int status;CHECK(waitpid(root,&status,0)==root&&WIFSTOPPED(status));long opts=PTRACE_O_EXITKILL|PTRACE_O_TRACEEXEC|PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK|PTRACE_O_TRACECLONE|PTRACE_O_TRACESYSGOOD;
 pt(PTRACE_SETOPTIONS,root,NULL,(void*)opts);pt(PTRACE_CONT,root,NULL,NULL);int answer=-1;
 while(1){pid_t t=waitpid(-1,&status,__WALL);if(t<0){if(errno==EINTR)continue;CHECK(errno==ECHILD);break;}struct state*st=state(t);
  if(WIFEXITED(status)||WIFSIGNALED(status)){
   if(t==root)answer=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
   fprintf(ledger,"%u EXIT %d %d\n",++seq,t,WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status));*st=ts[--nt];continue;
  }
  CHECK(WIFSTOPPED(status));int signal=WSTOPSIG(status),ev=(unsigned)status>>16,deliver=0;
  if(ev==PTRACE_EVENT_EXEC){logexec(t);if(t==root&&same_exe(t)){base=image_base(t);st->cargo=1;setdbg(t);fprintf(ledger,"%u ENROLLED %d %lx\n",++seq,t,base);}}
  else if(ev==PTRACE_EVENT_FORK||ev==PTRACE_EVENT_VFORK||ev==PTRACE_EVENT_CLONE){} 
  else if(signal==(SIGTRAP|0x80)&&st->cargo)syscall_stop(st);
  else if(signal==SIGSTOP){if(tgroup(t)==root&&base){st->cargo=1;setdbg(t);}else if(base){pt(PTRACE_POKEUSER,t,(void*)offsetof(struct user,u_debugreg[7]),0);}}
  else if(signal==SIGTRAP&&st->cargo){struct user_regs_struct reg;pt(PTRACE_GETREGS,t,0,&reg);int k=-1;for(int i=0;i<4;i++)if(reg.rip==base+loc[i])k=i;CHECK(k>=0);
   unsigned long witness=k>=2?reg.rip-base:(unsigned long)pt(PTRACE_PEEKDATA,t,(void*)reg.rsp,0)-base;
   unsigned long length=0;unsigned b=0;
   if(k==0){st->result_slot=reg.rdi;if(reg.rdx){length=reg.rcx;b=capture(t,reg.rdx,length);}}
   if(k>=2){
    CHECK(st->result_slot);unsigned long words[3];
    struct iovec dst={words,sizeof(words)},src={(void*)st->result_slot,sizeof(words)};
    CHECK(process_vm_readv(t,&dst,1,&src,1,0)==sizeof(words));length=words[2];CHECK(length<=words[0]&&length<1024*1024);b=capture(t,words[1],length);st->result_slot=0;
   }
   fprintf(ledger,"%u FUNCTION %d %s %lx %lu %u\n",++seq,t,labels[k],witness,length,b);
   if(k==1 && strcmp(actor,"-")&&!swapped++){for(int fd=0;fd<8192;fd++)CHECK(!fds[fd]);
    pid_t helper=fork();CHECK(helper>=0);if(!helper){execl("/usr/bin/python3","python3","-IB",actor,lockpath,output,NULL);_exit(126);}
    int hs;CHECK(waitpid(helper,&hs,0)==helper && WIFEXITED(hs)&&WEXITSTATUS(hs)==0);fprintf(ledger,"%u CHANGED %d\n",++seq,t);}
  }else deliver=signal;
  pt(st->cargo?PTRACE_SYSCALL:PTRACE_CONT,t,NULL,(void*)(intptr_t)deliver);
 }
 CHECK(answer>=0);fprintf(ledger,"%u RESULT %d\n",++seq,answer);fclose(ledger);return answer;
}
