#include <uapi/linux/ptrace.h>
#include <linux/sched.h>
#include <linux/fs.h>
#include <linux/mm_types.h>
#include <linux/sched/cputime.h>
#define PAY 2048
struct ev { u64 ns, ino, x[10]; u32 type, tid, tgid, owner, dev, off, len, total; char data[PAY]; };
BPF_PERCPU_ARRAY(scratch,struct ev,1);
BPF_HASH(members,u32,u32,8192);
BPF_HASH(cargos,u32,u32,128);
struct syscall_clock {u64 ts, nr, arg;};
BPF_HASH(syscalls,u32,struct syscall_clock,4096);
BPF_PERF_OUTPUT(out);
static inline __attribute__((always_inline)) struct ev *start(u32 type,u32 owner){
    u32 zero=0;struct ev *e=scratch.lookup(&zero);if(!e)return 0;
    u64 id=bpf_get_current_pid_tgid();e->ns=bpf_ktime_get_ns();e->tid=(u32)id;e->tgid=id>>32;e->type=type;e->owner=owner;
    e->dev=0;e->ino=0;e->off=0;e->len=0;e->total=0;
    return e;
}
#define HEAD __builtin_offsetof(struct ev,data)
TRACEPOINT_PROBE(sched,sched_process_fork){
    u32 parent=args->parent_pid,child=args->child_pid,*m=members.lookup(&parent);
    if(!m)return 0;
    u32 own=*m;members.update(&child,&own);
    struct ev *e=start(1,own);if(e){e->off=child;out.perf_submit(args,e,HEAD);}return 0;
}
TRACEPOINT_PROBE(sched,sched_process_exec){
    u32 id=(u32)bpf_get_current_pid_tgid(),old=args->old_pid;
    u32 *m=members.lookup(&id);if(!m){m=members.lookup(&old);if(!m)return 0;}
    u32 own=*m;
    struct task_struct *t=(struct task_struct*)bpf_get_current_task();
    struct mm_struct *mm=t->mm;struct inode *i=mm->exe_file->f_inode;
    u64 ino=i->i_ino;u32 dev=i->i_sb->s_dev;
    if(ino==WILD_INO && dev==WILD_DEV)own=id;
    members.update(&id,&own);
    u32 yes=1;if((ino==CARGO_A_INO && dev==CARGO_A_DEV)||(ino==CARGO_B_INO && dev==CARGO_B_DEV))cargos.update(&id,&yes);else cargos.delete(&id);
    struct ev *e=start(2,own);if(!e)return 0;
    e->ino=ino;e->dev=dev;e->off=old;
    unsigned long from=mm->arg_start,to=mm->arg_end;
    if(to<from || to-from>524288){e->total=0xffffffff;out.perf_submit(args,e,HEAD);return 0;}
    u32 total=(u32)(to-from);e->total=total;out.perf_submit(args,e,HEAD);
    #pragma clang loop unroll(disable)
    for(u32 off=0;off<524288;off+=PAY){
        if(off>=total)break;
        u32 bytes=total-off;if(bytes>PAY)bytes=PAY;
        if(bytes==0)break;
        e->type=3;e->off=off;e->len=bytes;
        int err=bpf_probe_read_user(&e->data,bytes,(void*)(from+off));
        if(err){e->type=7;e->len=0;out.perf_submit(args,e,HEAD);break;}
        out.perf_submit(args,e,HEAD+bytes);
    }
    return 0;
}
TRACEPOINT_PROBE(sched,sched_process_exit){
    u32 id=(u32)bpf_get_current_pid_tgid(),*m=members.lookup(&id);if(!m)return 0;
    u32 own=*m;struct ev *e=start(4,own);
    if(e){struct task_struct *t=(struct task_struct*)bpf_get_current_task();e->off=t->exit_code;
    e->x[0]=t->se.sum_exec_runtime;e->x[1]=t->sched_info.run_delay;
    e->x[2]=t->min_flt;e->x[3]=t->maj_flt;e->x[4]=t->ioac.read_bytes;e->x[5]=t->ioac.write_bytes;
    e->x[6]=t->nvcsw;e->x[7]=t->nivcsw;e->x[8]=t->utime;e->x[9]=t->stime;
    out.perf_submit(args,e,HEAD);}
    members.delete(&id);return 0;
}

TRACEPOINT_PROBE(raw_syscalls,sys_enter){
    u64 id=bpf_get_current_pid_tgid();u32 tgid=id>>32,tid=(u32)id;
    if(args->id==1 && (args->args[0]==1 || args->args[0]==2)){
        u32 *m=members.lookup(&tid);
        if(m && *m){
            struct ev *e=start(5,*m);
            if(e){
                u32 sz=(u32)args->args[2];sz=sz>240?240:sz;
                if (sz>0 && sz<=240){
                    e->off=(u32)args->args[0];e->len=sz;
                    int rc=bpf_probe_read_user(e->data,sz,(void*)args->args[1]);
                    if(rc){e->type=9;e->len=0;e->x[0]=rc;out.perf_submit(args,e,HEAD);}
                    else out.perf_submit(args,e,HEAD+sz);
                }
            }
        }
    }
    if(!cargos.lookup(&tgid))return 0;
    struct syscall_clock c={.ts=bpf_ktime_get_ns(),.nr=args->id,.arg=args->args[0]};
    syscalls.update(&tid,&c);return 0;
}
TRACEPOINT_PROBE(raw_syscalls,sys_exit){
    u32 id=(u32)bpf_get_current_pid_tgid(),tg=bpf_get_current_pid_tgid()>>32;
    if(!cargos.lookup(&tg))return 0;
    struct syscall_clock *c=syscalls.lookup(&id);if(!c)return 0;
    u64 now=bpf_ktime_get_ns();
    if(now-c->ts>=5000000){
      struct ev *e=start(6,0);if(e){e->x[0]=c->ts;e->x[1]=c->nr;e->x[2]=c->arg;e->x[3]=args->ret;out.perf_submit(args,e,HEAD);}
    }
    syscalls.delete(&id);return 0;
}
