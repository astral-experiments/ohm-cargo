// Linux/x86-64 observer for one unprivileged Cargo build. The tracee receives no flags or environment changes.
#include <sys/ptrace.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/uio.h>
#include <linux/fs.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <unordered_map>
#include <vector>

namespace fs = std::filesystem;
struct Thread { bool selected = false; long call = -1; unsigned long arg[6]{}; };
static std::unordered_map<pid_t, Thread> threads;
static fs::path output, compiler, unit, origin;
static FILE* events;
static unsigned captures, selected, publications, clones, execs;
static bool after_meta;
static int held_old = -1;

[[noreturn]] static void fail(const char* message) {
    std::perror(message);
    std::exit(90);
}
static std::string proc(pid_t p, const std::string& leaf) {
    return "/proc/" + std::to_string(p) + "/" + leaf;
}
static std::string fdpath(pid_t p, unsigned long fd) {
    return proc(p, "fd/" + std::to_string(fd));
}
static bool same_inode(const fs::path& first, const fs::path& second) {
    struct stat a{}, b{};
    return stat(first.c_str(), &a) == 0 && stat(second.c_str(), &b) == 0 &&
           a.st_dev == b.st_dev && a.st_ino == b.st_ino;
}
static std::string path_of(const fs::path& link) {
    std::error_code error;
    auto result = fs::read_symlink(link, error);
    return error ? std::string() : result.string();
}
static std::string argstr(pid_t p, unsigned long addr) {
    char buf[4096]{};
    iovec local{buf, sizeof buf}, remote{reinterpret_cast<void*>(addr), sizeof buf};
    auto n = process_vm_readv(p, &local, 1, &remote, 1, 0);
    return n > 0 ? std::string(buf, strnlen(buf, n)) : std::string();
}
static bool on_exec(pid_t p) {
    std::ifstream file(proc(p, "cmdline"), std::ios::binary);
    std::string all{std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
    if (all.empty() || all.back()) fail("read exec arguments");
    std::vector<std::string> args;
    for (size_t i = 0; i < all.size(); i += args.back().size() + 1) args.emplace_back(all.c_str() + i);
    bool is_compiler = same_inode(proc(p, "exe"), compiler);
    std::string crate;
    bool full = false, lib = false, hint = false;
    for (size_t i = 1; i < args.size(); ++i) {
        if (args[i] == "--crate-name" && i + 1 < args.size()) crate = args[i + 1];
        if (args[i] == "--crate-type" && i + 1 < args.size()) lib |= args[i + 1] == "lib";
        full |= args[i] == "--emit=dep-info,metadata,link";
        if (args[i].starts_with("-Zohm-rlib-origin=")) {
            if (hint) fail("duplicate origin hint");
            hint = true;
        }
    }
    auto exe = path_of(proc(p, "exe"));
    std::ofstream dst(output / ("exec-" + std::to_string(execs) + ".argv"), std::ios::binary);
    dst.write(all.data(), all.size());
    dst.close();
    if (!dst) fail("save exec arguments");
    std::fprintf(events, "exec\t%u\t%d\t%d\t%s\t%s\n", execs++, p, is_compiler, exe.c_str(), crate.c_str());
    bool root = is_compiler && full && lib && crate == "ruff_linter";
    if (root) {
        if (++selected != 1 || hint != (origin != "-")) fail("select root compiler and hint");
        if (hint) {
            bool exact = false;
            for (const auto& a : args) exact |= a == "-Zohm-rlib-origin=" + origin.string();
            if (!exact) fail("wrong compiler origin");
        }
        std::fprintf(events, "selected\t%d\n", p);
    }
    std::fflush(events);
    return root;
}
static void on_open(pid_t p, unsigned long fd) {
    auto real = fdpath(p, fd);
    auto path = path_of(real);
    auto name = fs::path(path).filename().string();
    bool metadata = name == "lib.rmeta" || name == "lib.rmeta-link";
    bool cgu = name.starts_with("ruff_linter-") && name.ends_with(".rcgu.o");
    if (!metadata && !(after_meta && cgu)) return;
    after_meta |= metadata;
    if (publications || captures >= 258) fail("unexpected archive input");
    int in = open(real.c_str(), O_RDONLY | O_CLOEXEC);
    int out = open((output/("input-"+std::to_string(captures))).c_str(), O_CREAT|O_EXCL|O_WRONLY, 0600);
    if (in < 0 || out < 0) fail("open witness input");
    struct stat a{}, b{};
    if (fstat(in, &a) || !S_ISREG(a.st_mode)) fail("initial stat");
    char buf[65536];
    off_t off = 0;
    while (off < a.st_size) {
        auto n = pread(in, buf, sizeof buf, off);
        if (n < 1) fail("read witness input");
        for (ssize_t i = 0; i < n;) {
            auto w = write(out, buf+i, n-i);
            if (w < 1) fail("write witness input");
            i += w;
        }
        off += n;
    }
    if (pread(in, buf, 1, off) != 0 || fstat(in, &b) || a.st_dev != b.st_dev || a.st_ino != b.st_ino ||
        a.st_size != b.st_size || a.st_ctim.tv_sec != b.st_ctim.tv_sec || a.st_ctim.tv_nsec != b.st_ctim.tv_nsec)
        fail("input changed while observed");
    if (close(out) || close(in)) fail("close witness input");
    std::fprintf(events, "input\t%u\t%d\t%llu\t%llu\t%lld\t%s\n", captures++, p,
                 (unsigned long long)a.st_dev, (unsigned long long)a.st_ino, (long long)a.st_size, path.c_str());
    std::fflush(events);
}
static void on_exit(pid_t p, Thread& t, long result) {
    long n = t.call;
    if ((n == SYS_openat && (t.arg[2]&O_ACCMODE) == O_RDONLY) ||
        (n == SYS_open && (t.arg[1]&O_ACCMODE) == O_RDONLY)) on_open(p, result);
    if (n == SYS_ioctl && t.arg[1] == FICLONE) {
        auto dst = path_of(fdpath(p, t.arg[0])), src = path_of(fdpath(p, t.arg[2]));
        auto held_path = fdpath(getpid(), held_old);
        bool same = origin != "-" && same_inode(fdpath(p, t.arg[2]), origin) &&
                    same_inode(fdpath(p, t.arg[2]), held_path);
        fs::path target(dst);
        bool temp = target.filename() == "tmp.a" && target.parent_path().filename().string().ends_with(".temp-archive") &&
                    target.parent_path().parent_path() == unit.parent_path();
        if (same && temp) ++clones;
        std::fprintf(events,"clone\t%d\t%ld\t%d\t%d\t%s\t%s\n",p,result,same,temp,src.c_str(),dst.c_str());
    }
    if (n == SYS_rename || n == SYS_renameat || n == SYS_renameat2) {
        auto a = argstr(p,t.arg[n == SYS_rename ? 0 : 1]), b = argstr(p,t.arg[n == SYS_rename ? 1 : 3]);
        if (b == unit) {
            ++publications;
            std::fprintf(events,"publish\t%d\t%s\t%s\n",p,a.c_str(),b.c_str());
        }
    }
    std::fflush(events);
}
int main(int argc, char** argv) {
    if (argc < 7 || std::string(argv[5]) != "--") {
        std::fputs("capture DIR RUSTC UNIT ORIGIN_OR_DASH -- COMMAND [ARGS...]\n",stderr);
        return 2;
    }
    output=argv[1]; compiler=argv[2]; unit=argv[3]; origin=argv[4];
    if (!fs::is_directory(output) || !fs::is_empty(output) || !unit.is_absolute() || !fs::is_regular_file(compiler)) return 2;
    held_old = open(unit.c_str(), O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if (held_old < 0 || (origin != "-" && !same_inode(fdpath(getpid(), held_old), origin)))
        fail("hold original archive inode");
    events = std::fopen((output/"events.tsv").c_str(),"wx");
    if (!events) fail("events");
    pid_t root = fork();
    if (root < 0) fail("fork");
    if (root == 0) {
        if (ptrace(PTRACE_TRACEME,0,nullptr,nullptr)<0) _exit(92);
        raise(SIGSTOP); execvp(argv[6],argv+6); _exit(93);
    }
    int status = 0, rootrc = -1;
    if (waitpid(root,&status,0) != root) fail("wait root");
    unsigned long opts = PTRACE_O_TRACECLONE|PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK|
                         PTRACE_O_TRACEEXEC|PTRACE_O_TRACESYSGOOD|PTRACE_O_EXITKILL;
    if (ptrace(PTRACE_SETOPTIONS,root,0,opts)<0 || ptrace(PTRACE_CONT,root,0,0)<0) fail("start tracing");
    threads[root] = {};
    while (true) {
        pid_t p = waitpid(-1,&status,__WALL);
        if (p < 0) { if (errno==EINTR) continue; if (errno==ECHILD) break; fail("wait"); }
        if (WIFEXITED(status) || WIFSIGNALED(status)) {
            int rc = WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
            if (p==root) rootrc=rc;
            std::fprintf(events,"exit\t%d\t%d\n",p,rc);
            threads.erase(p);
            continue;
        }
        if (!WIFSTOPPED(status)) continue;
        Thread& t=threads[p]; int event=status>>16, sig=WSTOPSIG(status), deliver=0;
        if (event==PTRACE_EVENT_FORK || event==PTRACE_EVENT_CLONE || event==PTRACE_EVENT_VFORK) {
            unsigned long child=0; if (ptrace(PTRACE_GETEVENTMSG,p,0,&child)<0) fail("new process");
            bool inherited=t.selected; threads[child].selected=inherited;
        } else if (event==PTRACE_EVENT_EXEC) {
            t.selected=on_exec(p); t.call=-1;
        } else if (sig==(SIGTRAP|0x80) && t.selected) {
            __ptrace_syscall_info info{};
            if (ptrace(PTRACE_GET_SYSCALL_INFO,p,sizeof info,&info)<0) fail("syscall information");
            if (info.op==PTRACE_SYSCALL_INFO_ENTRY) {
                t.call=info.entry.nr; for (int k=0;k<6;k++) t.arg[k]=info.entry.args[k];
            } else if (info.op==PTRACE_SYSCALL_INFO_EXIT && !info.exit.is_error) on_exit(p,t,info.exit.rval);
        } else if (sig!=SIGSTOP && sig!=SIGTRAP) deliver=sig;
        if (ptrace(threads[p].selected ? PTRACE_SYSCALL : PTRACE_CONT,p,0,deliver)<0 && errno!=ESRCH)
            fail("resume");
    }
    std::fprintf(events,"terminal\t%d\t%u\t%u\t%u\t%u\n",rootrc,selected,captures,publications,clones);
    if (std::fclose(events)) fail("close events");
    return rootrc==0 && selected==1 && captures==258 && publications==1 && clones==(origin!="-" ? 1u : 0u) ? 0 : 96;
}
