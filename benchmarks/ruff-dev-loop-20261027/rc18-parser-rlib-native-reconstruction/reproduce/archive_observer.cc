#define _GNU_SOURCE
#include <sys/ptrace.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <limits.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>
#include <algorithm>
struct State {bool selected=false; long syscall=-1;unsigned long a[6]={};};
static std::unordered_map<pid_t,State> states;static std::string out;static FILE *events;static size_t files=0;static int matches=0;static bool sawmeta=false;
static void die(const char*s){perror(s);exit(90);}static std::string fdpath(int p,int fd){char path[100],buf[PATH_MAX+1];snprintf(path,sizeof path,"/proc/%d/fd/%d",p,fd);auto n=readlink(path,buf,PATH_MAX);return n>0?std::string(buf,n):"";}
static std::string argstr(pid_t p,unsigned long addr){char buf[PATH_MAX+1]={};struct iovec me={buf,PATH_MAX},them={(void*)addr,PATH_MAX};auto n=process_vm_readv(p,&me,1,&them,1,0);return n>0?std::string(buf,strnlen(buf,n)):"";}
static bool parser(pid_t p){std::string f="/proc/"+std::to_string(p)+"/cmdline";int fd=open(f.c_str(),O_RDONLY);char buf[262144];ssize_t n=fd<0?-1:read(fd,buf,sizeof buf);if(fd>=0)close(fd);if(n<1)return false;std::vector<std::string> a;for(ssize_t i=0;i<n;){auto l=strnlen(buf+i,n-i);a.emplace_back(buf+i,l);i+=l+1;}if(a.empty()||!a[0].ends_with("/rustc"))return false;for(size_t i=1;i+1<a.size();i++)if(a[i]=="--crate-name"&&a[i+1]=="ruff_python_parser"){return std::find(a.begin(),a.end(),"lib")!=a.end() && std::find(a.begin(),a.end(),"link-only")==a.end();}return false;}
static void opened(pid_t p,int fd){std::string path=fdpath(p,fd);auto name=path.substr(path.find_last_of('/')+1);bool meta=name=="lib.rmeta"||name=="lib.rmeta-link";bool obj=name.starts_with("ruff_python_parser-")&&name.ends_with(".rcgu.o");if(!meta&&!(sawmeta&&obj))return;sawmeta|=meta;std::string src="/proc/"+std::to_string(p)+"/fd/"+std::to_string(fd);int in=open(src.c_str(),O_RDONLY|O_CLOEXEC);if(in<0)die("open acquired");struct stat a,b;if(fstat(in,&a)||!S_ISREG(a.st_mode))die("acquired type");std::string copy=out+"/input-"+std::to_string(files);int w=open(copy.c_str(),O_CREAT|O_EXCL|O_WRONLY,0600);if(w<0)die("open evidence");char buf[1<<16];off_t at=0;while(at<a.st_size){auto n=pread(in,buf,sizeof buf,at);if(n<=0)die("pread acquired");for(ssize_t k=0;k<n;){auto m=write(w,buf+k,n-k);if(m<=0)die("write evidence");k+=m;}at+=n;}char end;if(pread(in,&end,1,at)!=0||fstat(in,&b)||a.st_ino!=b.st_ino||a.st_dev!=b.st_dev||a.st_size!=b.st_size||a.st_ctim.tv_sec!=b.st_ctim.tv_sec||a.st_ctim.tv_nsec!=b.st_ctim.tv_nsec)die("unstable acquired input");close(in);close(w);fprintf(events,"input\t%zu\t%d\t%llu\t%llu\t%lld\t%s\n",files++,p,(unsigned long long)a.st_dev,(unsigned long long)a.st_ino,(long long)at,path.c_str());fflush(events);}
int main(int argc,char**argv){if(argc<3)return 2;out=argv[1];events=fopen((out+"/events.tsv").c_str(),"wx");if(!events)die("events");pid_t root=fork();if(!root){if(ptrace(PTRACE_TRACEME,0,0,0)<0)_exit(92);raise(SIGSTOP);execvp(argv[2],argv+2);_exit(93);}int status;waitpid(root,&status,0);unsigned long opt=PTRACE_O_TRACECLONE|PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK|PTRACE_O_TRACEEXEC|PTRACE_O_TRACESYSGOOD|PTRACE_O_EXITKILL;if(ptrace(PTRACE_SETOPTIONS,root,0,opt)<0)die("setoptions");states[root]=State{};if(ptrace(PTRACE_CONT,root,0,0)<0)die("continue");int rootret=-1;for(;;){pid_t p=waitpid(-1,&status,__WALL);if(p<0){if(errno==EINTR)continue;if(errno==ECHILD)break;die("wait");}if(WIFEXITED(status)||WIFSIGNALED(status)){if(p==root)rootret=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);states.erase(p);continue;}if(!WIFSTOPPED(status))continue;const int sig=WSTOPSIG(status),event=status>>16;int deliver=0;State&s=states[p];if(event==PTRACE_EVENT_CLONE||event==PTRACE_EVENT_FORK||event==PTRACE_EVENT_VFORK){unsigned long kid=0;if(ptrace(PTRACE_GETEVENTMSG,p,0,&kid)<0)die("offspring");bool selected=s.selected;states[kid].selected=selected;}else if(event==PTRACE_EVENT_EXEC){s.selected=parser(p);s.syscall=-1;if(s.selected){++matches;fprintf(events,"parser\t%d\n",p);fflush(events);}}else if(sig==(SIGTRAP|0x80)&&s.selected){__ptrace_syscall_info i={};if(ptrace(PTRACE_GET_SYSCALL_INFO,p,sizeof i,&i)<0)die("get syscall");if(i.op==PTRACE_SYSCALL_INFO_ENTRY){s.syscall=i.entry.nr;for(int k=0;k<6;k++)s.a[k]=i.entry.args[k];}else if(i.op==PTRACE_SYSCALL_INFO_EXIT&&!i.exit.is_error){long n=s.syscall;if((n==SYS_openat&&(s.a[2]&O_ACCMODE)==O_RDONLY)||(n==SYS_open&&(s.a[1]&O_ACCMODE)==O_RDONLY))opened(p,i.exit.rval);if(n==SYS_link||n==SYS_linkat){auto old=argstr(p,s.a[n==SYS_link?0:1]),nw=argstr(p,s.a[n==SYS_link?1:3]);if(old.ends_with(".o")||nw.ends_with(".o")){fprintf(events,"link\t%d\t%s\t%s\n",p,old.c_str(),nw.c_str());fflush(events);}}if(n==SYS_rename||n==SYS_renameat||n==SYS_renameat2){auto old=argstr(p,s.a[n==SYS_rename?0:1]),nw=argstr(p,s.a[n==SYS_rename?1:3]);if(nw.ends_with(".rlib")){fprintf(events,"publish\t%d\t%s\t%s\n",p,old.c_str(),nw.c_str());fflush(events);}}}}else if(sig!=SIGSTOP&&sig!=SIGTRAP)deliver=sig;if(ptrace(states[p].selected?PTRACE_SYSCALL:PTRACE_CONT,p,0,deliver)<0&&errno!=ESRCH)die("resume");}fprintf(events,"terminal\t%d\t%d\t%zu\n",rootret,matches,files);fclose(events);return rootret<0?94:rootret;}
