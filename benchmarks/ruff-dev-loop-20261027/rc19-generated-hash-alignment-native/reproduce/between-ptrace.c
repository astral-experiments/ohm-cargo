#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <linux/ptrace.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 7) return 110;
    const char *cargo = argv[1], *watch = argv[2], *replace = argv[3];
    int fd = open(argv[4], O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC, 0600);
    struct stat executable;
    if (fd < 0 || stat(cargo, &executable) != 0) return 111;
    pid_t root = fork();
    if (root == 0) {
        if (ptrace(PTRACE_TRACEME, 0, 0, 0) < 0) _exit(112);
        raise(SIGSTOP); execvp(argv[5], argv + 5); _exit(113);
    }
    int status, exit_code = -1, opens = 0;
    if (root < 0 || waitpid(root, &status, 0) != root || !WIFSTOPPED(status)) return 114;
    unsigned opts = PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEFORK | PTRACE_O_TRACEVFORK |
                    PTRACE_O_TRACECLONE | PTRACE_O_TRACEEXEC | PTRACE_O_EXITKILL;
    if (ptrace(PTRACE_SETOPTIONS,root,0,(void *)(uintptr_t)opts)<0 ||
        ptrace(PTRACE_SYSCALL,root,0,0)<0) return 115;
    size_t n = strlen(watch) + 1;
    if (n >= PATH_MAX) return 116;
    for (;;) {
        pid_t p = waitpid(-1,&status,__WALL);
        if (p < 0) {
            if (errno == EINTR) continue;
            if (errno == ECHILD) break;
            return 117;
        }
        if (WIFEXITED(status) || WIFSIGNALED(status)) {
            if (p == root) exit_code=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
            continue;
        }
        if (!WIFSTOPPED(status)) return 118;
        int signal = WSTOPSIG(status);
        if (signal == (SIGTRAP|0x80)) {
            struct ptrace_syscall_info info;
            if (ptrace(PTRACE_GET_SYSCALL_INFO,p,sizeof(info),&info)<0) return 119;
            if (info.op==PTRACE_SYSCALL_INFO_ENTRY &&
                (info.entry.nr==SYS_openat || info.entry.nr==SYS_open || info.entry.nr==SYS_openat2)) {
                char contents[PATH_MAX], proc[100]; struct stat ex;
                int index=info.entry.nr==SYS_open?0:1;
                struct iovec l={contents,n},r={(void *)(uintptr_t)info.entry.args[index],n};
                if (process_vm_readv(p,&l,1,&r,1,0)==(ssize_t)n && memcmp(contents,watch,n)==0) {
                    snprintf(proc,sizeof(proc),"/proc/%d/exe",p);
                    if (stat(proc,&ex)==0 && ex.st_dev==executable.st_dev && ex.st_ino==executable.st_ino) {
                        opens++; int did=0;
                        if (opens==2 && strcmp(replace,"-")!=0) {
                            if (rename(replace,watch)<0) return 120;
                            did=1;
                        }
                        dprintf(fd,"cargo-open %u pid %d mutated %d\n",opens,p,did);
                    }
                }
            }
            signal=0;
        } else if (signal==SIGSTOP || signal==SIGTRAP) {signal=0;}
        if (ptrace(PTRACE_SYSCALL,p,0,(void *)(uintptr_t)signal)<0 && errno!=ESRCH) return 121;
    }
    dprintf(fd,"terminal opens %d exit %d\n",opens,exit_code);close(fd);
    if (opens<2) return 122;
    return exit_code;
}
