#include "dr_api.h"
#include "drmgr.h"
#include <stdint.h>
#include <string.h>

/* These offsets are specific to the release-PGO Cargo ELF recorded in plan.json. */
enum event { NORMAL, PREPARE, BEGIN_RANGE, FOLD, EDGE, CLONE, LOOKUP, INSERT, END_RANGE };
typedef struct {
    uint64_t total, entered_at, prepared, completed;
    uint64_t folds, edges, clones, lookups, inserts;
    bool active;
} counter_t;
static app_pc base;
static file_t sink;
static void *output_lock;
static int slot;
static uint64_t owner;
static uint64_t kernel_pid(void) {
    /* Get the actual executing process even when DynamoRIO flushes inherited
       thread contexts in a multithreaded fork child just before exec. */
    unsigned long result;
    __asm__ volatile("syscall" : "=a"(result) : "a"(39UL) : "rcx","r11","memory");
    return result;
}


static int marker(app_pc pc) {
    if (!base || pc < base) return NORMAL;
    switch ((uintptr_t)pc - (uintptr_t)base) {
    case 0x1168a80: return PREPARE;
    case 0x116d8cb: return BEGIN_RANGE;
    case 0xf93d60: return FOLD;
    case 0xf93dac: return EDGE;
    case 0xf93dee: return CLONE;
    case 0xf93ebc: return LOOKUP;
    case 0xf93f85: return INSERT;
    case 0x116d9ee: return END_RANGE;
    default: return NORMAL;
    }
}

static void add(uint n, uint e) {
    void *ctx=dr_get_current_drcontext();
    counter_t *c=drmgr_get_tls_field(ctx, slot);
    if (!c) dr_abort();
    if (e==PREPARE) c->prepared++;
    else if (e==BEGIN_RANGE) {
        DR_ASSERT(!c->active);
        c->active=true;
        c->entered_at=c->total;
        c->folds=c->edges=c->clones=c->lookups=c->inserts=0;
    } else if (e==END_RANGE) {
        if (!c->active || c->folds!=1 || c->edges<c->clones ||
            c->clones<c->lookups || c->lookups!=c->inserts) dr_abort();
        c->active=false;
        c->completed++;
        dr_mutex_lock(output_lock);
        if (kernel_pid()!=owner) dr_abort();
        dr_fprintf(sink,"R %u %llu %llu %llu %llu %llu %llu\n",dr_get_thread_id(ctx),
             c->total-c->entered_at,c->folds,c->edges,c->clones,c->lookups,c->inserts);
        dr_mutex_unlock(output_lock);
    } else if (e!=NORMAL) {
        if (!c->active) dr_abort();
        if(e==FOLD)c->folds++;
        if(e==EDGE)c->edges++;
        if(e==CLONE)c->clones++;
        if(e==LOOKUP)c->lookups++;
        if(e==INSERT)c->inserts++;
    }
    c->total+=n;
}

static dr_emit_flags_t block(void *ctx,void *tag,instrlist_t *bb,instr_t *inst,bool for_trace,bool translating,void *data) {
    if(!drmgr_is_first_instr(ctx,inst)) return DR_EMIT_DEFAULT;
    drmgr_disable_auto_predication(ctx,bb);
    for(instr_t *s=instrlist_first_app(bb);s!=NULL;) {
        uint n=1;
        uint e=marker(instr_get_app_pc(s));
        instr_t *next=instr_get_next_app(s);
        while(next && marker(instr_get_app_pc(next))==NORMAL) {
            n++;next=instr_get_next_app(next);
        }
        dr_insert_clean_call(ctx,bb,s,(void *)add,false,2,OPND_CREATE_INT32(n),OPND_CREATE_INT32(e));
        s=next;
    }
    return DR_EMIT_DEFAULT;
}
static void start(void *ctx) {
    counter_t *c=dr_thread_alloc(ctx,sizeof(*c));memset(c,0,sizeof(*c));drmgr_set_tls_field(ctx,slot,c);
    if(kernel_pid()!=owner) return;
    dr_mutex_lock(output_lock);dr_fprintf(sink,"T %u\n",dr_get_thread_id(ctx));dr_mutex_unlock(output_lock);
}
static void end(void *ctx) {
    if(kernel_pid()!=owner) return;
    counter_t *c=drmgr_get_tls_field(ctx,slot);
    if(c->active || c->prepared!=c->completed) dr_abort();
    dr_mutex_lock(output_lock);
    dr_fprintf(sink,"F %u %llu %llu %llu\n",dr_get_thread_id(ctx),c->total,c->prepared,c->completed);
    dr_mutex_unlock(output_lock);dr_thread_free(ctx,c,sizeof(*c));
}
static void finish(void) {
    if(kernel_pid()!=owner) return;
    dr_fprintf(sink,"P %u\n",dr_get_process_id());dr_close_file(sink);
    drmgr_unregister_tls_field(slot);dr_mutex_destroy(output_lock);drmgr_exit();
}
DR_EXPORT void dr_client_main(client_id_t id,int argc,const char *argv[]) {
    if(argc!=2 || !drmgr_init()) dr_abort();
    owner=kernel_pid(); if(owner!=dr_get_process_id()) dr_abort();
    module_data_t *m=dr_get_main_module();base=m->start;
    sink=dr_open_file(argv[1],DR_FILE_WRITE_OVERWRITE|DR_FILE_ALLOW_LARGE);
    if(sink==INVALID_FILE)dr_abort();
    dr_fprintf(sink,"B %u %s\n",dr_get_process_id(),m->full_path);dr_free_module_data(m);
    output_lock=dr_mutex_create();slot=drmgr_register_tls_field();
    if(slot<0 || !drmgr_register_thread_init_event(start) || !drmgr_register_thread_exit_event(end) ||
       !drmgr_register_bb_instrumentation_event(NULL,block,NULL)) dr_abort();
    drmgr_register_exit_event(finish);
}
