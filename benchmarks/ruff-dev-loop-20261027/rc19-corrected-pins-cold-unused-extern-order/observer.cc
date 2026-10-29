#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <vector>
#include <fcntl.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <unistd.h>
namespace fs=std::filesystem;
struct Job { std::string name; fs::path out; };
static std::map<pid_t,pid_t> family;
static std::map<pid_t,Job> jobs;
static std::map<pid_t,std::string> pending,partial;
static fs::path dest;
static std::ofstream events;
static long long stamp(){
 return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
}
static void logline(pid_t pid,const std::string &type,const std::string &data){
 events<<stamp()<<'\t'<<pid<<'\t'<<family[pid]<<'\t'<<type<<'\t'<<data<<'\n';events.flush();
}
static std::string remote(pid_t pid,unsigned long addr,size_t n){
 std::string s(n,'\0');if(!n)return s;
 iovec local{s.data(),n},foreign{reinterpret_cast<void*>(addr),n};
 ssize_t got=process_vm_readv(pid,&local,1,&foreign,1,0);
 if(got<0)return {};
 s.resize(got);return s;
}
static void report_write(pid_t pid,const std::string &data){
 std::string &buffer=partial[pid];buffer+=data;
 size_t pos;
 while((pos=buffer.find('\n'))!=std::string::npos){
  auto line=buffer.substr(0,pos);buffer.erase(0,pos+1);
  if(line.find("\"unused_extern_names\"")!=std::string::npos){
   auto k=jobs.find(family[pid]);if(k==jobs.end())continue;
   logline(pid,"unused-return",line);
  }
 }
 if(buffer.size()>262144){logline(pid,"oversize-stderr",std::to_string(buffer.size()));buffer.clear();}
}
static void exec_event(pid_t pid){
 std::ifstream in("/proc/"+std::to_string(pid)+"/cmdline",std::ios::binary);
 std::vector<std::string> a;std::string item;
 while(std::getline(in,item,'\0'))a.push_back(item);
 if(a.empty())return;
 auto after=[&](const std::string &flag)->std::string{
  auto it=std::find(a.begin(),a.end(),flag);return it!=a.end()&&++it!=a.end()?*it:std::string();
 };
 std::string exe=fs::path(a[0]).filename(),name=after("--crate-name");
 if(exe=="rustc"&&(name=="fixtures"||name=="generate_inline_tests"||name=="e2e"||name=="ruff_python_parser"||name=="ty_server")){
  family[pid]=pid;
  fs::path out;
  if(name=="fixtures"||name=="generate_inline_tests"||name=="e2e"){
   std::string suffix;
   for(auto &x:a)if(x.starts_with("extra-filename="))suffix=x.substr(strlen("extra-filename="));
   if(!after("-o").empty())out=after("-o");
   else if(!after("--out-dir").empty()&&!suffix.empty())out=fs::path(after("--out-dir"))/(name+suffix);
  }
  jobs[pid]={name,out};logline(pid,"rustc-exec",name);
 }else if(family[pid]&&(exe=="cc"||exe=="gcc"||exe=="collect2"||exe=="ld.bfd"||exe=="ld"||exe=="ld.lld"||exe=="rust-lld")){
  logline(pid,"native-exec",exe+" "+after("-o"));
 }else return;
 std::ofstream raw(dest/("argv-"+std::to_string(pid)),std::ios::binary);
 for(auto &x:a)raw.write(x.c_str(),x.size()+1);
}
static void archive_output(pid_t pid,const Job &job){
 if(job.out.empty())return;
 int old=open(job.out.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
 if(old<0){logline(pid,"no-product",std::strerror(errno));return;}
 struct stat pre{},post{};if(fstat(old,&pre)||!S_ISREG(pre.st_mode)){close(old);return;}
 fs::path body=dest/("elf-"+std::to_string(pid));std::ofstream out(body,std::ios::binary);
 std::array<char,262144> buf;off_t total=0;ssize_t n;
 while((n=read(old,buf.data(),buf.size()))>0){out.write(buf.data(),n);total+=n;}
 out.close();fstat(old,&post);close(old);
 bool stable=n==0&&total==pre.st_size&&total==post.st_size&&pre.st_ino==post.st_ino&&pre.st_mtim.tv_sec==post.st_mtim.tv_sec&&pre.st_mtim.tv_nsec==post.st_mtim.tv_nsec;
 logline(pid,"product",job.name+" "+body.filename().string()+" "+std::to_string(total)+" "+std::to_string(pre.st_ino)+" "+(stable?"stable":"unstable"));
}
static void install(){
 sock_filter f[]={
  BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,nr)),
  BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,SYS_write,1,0),
  BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,SYS_writev,0,3),
  BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,args[0])),
  BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,2,0,1),
  BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_TRACE),
  BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)
 };
 sock_fprog p{static_cast<unsigned short>(sizeof(f)/sizeof(f[0])),f};
 if(prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)||prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&p)){perror("seccomp");_exit(125);}
}
int main(int argc,char**argv){
 if(argc<3)return 2;
 dest=argv[1];if(!fs::create_directory(dest))return 3;
 events.open(dest/"events.tsv");
 pid_t main=fork();if(main<0)return 4;
 if(!main){if(ptrace(PTRACE_TRACEME,0,0,0)<0)_exit(124);raise(SIGSTOP);install();execvp(argv[2],argv+2);_exit(127);}
 int status=0;if(waitpid(main,&status,0)!=main||!WIFSTOPPED(status))return 5;
 long options=PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK|PTRACE_O_TRACECLONE|PTRACE_O_TRACEEXEC|PTRACE_O_TRACEEXIT|PTRACE_O_TRACESECCOMP|PTRACE_O_TRACESYSGOOD|PTRACE_O_EXITKILL;
 if(ptrace(PTRACE_SETOPTIONS,main,0,options)<0){perror("ptrace");return 6;}
 ptrace(PTRACE_CONT,main,0,0);int result=126;std::set<pid_t> newborn;
 for(;;){
  pid_t pid=waitpid(-1,&status,__WALL);if(pid<0){if(errno==EINTR)continue;if(errno==ECHILD)break;return 7;}
  if(WIFEXITED(status)||WIFSIGNALED(status)){if(pid==main)result=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);family.erase(pid);pending.erase(pid);partial.erase(pid);continue;}
  if(!WIFSTOPPED(status))continue;
  int sig=WSTOPSIG(status),event=status>>16,deliver=0;auto resume=PTRACE_CONT;
  if(event==PTRACE_EVENT_CLONE||event==PTRACE_EVENT_FORK||event==PTRACE_EVENT_VFORK){
   unsigned long child=0;ptrace(PTRACE_GETEVENTMSG,pid,0,&child);family[child]=family[pid];newborn.insert(child);
  }else if(event==PTRACE_EVENT_EXEC){exec_event(pid);}
  else if(event==PTRACE_EVENT_EXIT){
   auto j=jobs.find(pid);
   if(j!=jobs.end()){unsigned long code=0;ptrace(PTRACE_GETEVENTMSG,pid,0,&code);logline(pid,"rustc-exit",j->second.name+" "+std::to_string(code));if(code==0)archive_output(pid,j->second);}
  }else if(event==PTRACE_EVENT_SECCOMP){
   if(family[pid]){
    user_regs_struct r{};if(ptrace(PTRACE_GETREGS,pid,0,&r)<0)return 8;
    auto &data=pending[pid];data.clear();
    if(r.orig_rax==SYS_write&&r.rdx<=524288)data=remote(pid,r.rsi,r.rdx);
    if(r.orig_rax==SYS_writev&&r.rdx<=128){
     auto bytes=remote(pid,r.rsi,r.rdx*sizeof(iovec));
     for(size_t i=0;i+sizeof(iovec)<=bytes.size();i+=sizeof(iovec)){
      iovec v{};memcpy(&v,bytes.data()+i,sizeof v);if(data.size()+v.iov_len>524288)break;
      data+=remote(pid,reinterpret_cast<unsigned long>(v.iov_base),v.iov_len);
     }
    }
    resume=PTRACE_SYSCALL;
   }
  }else if(sig==(SIGTRAP|0x80)){
   auto it=pending.find(pid);if(it!=pending.end()){user_regs_struct r{};ptrace(PTRACE_GETREGS,pid,0,&r);auto n=static_cast<long>(r.rax);if(n>0)report_write(pid,it->second.substr(0,n));pending.erase(it);}
  }else if(sig==SIGSTOP&&newborn.erase(pid)){}
  else if(sig!=SIGTRAP)deliver=sig;
  if(pending.count(pid))resume=PTRACE_SYSCALL;
  if(ptrace(resume,pid,0,deliver)<0&&errno!=ESRCH){perror("resume");return 9;}
 }
 return result;
}
