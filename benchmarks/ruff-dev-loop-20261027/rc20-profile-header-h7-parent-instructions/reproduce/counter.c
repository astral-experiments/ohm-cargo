#include "dr_api.h"
#include "drmgr.h"
#include <stdint.h>
#include <string.h>
#include "sites.h"
typedef struct { uint64_t instructions, decodes, graphs, inclusive, finished; bool live; } totals_t;
static app_pc base;
static int slot;
static file_t output;
static void *lock;
static bool calibration, scope_toy;
static unsigned long owner;
static unsigned long kernel_pid(void) {
    unsigned long value;
    __asm__ volatile("syscall" : "=a"(value) : "a"(39UL) : "rcx","r11","memory");
    return value;
}
static unsigned marker(app_pc pc) {
    if (pc < base) return 0;
    uintptr_t rva = (uintptr_t)pc - (uintptr_t)base;
    if (calibration) return rva == TOY_LOOP ? 1 : 0;
    if (scope_toy) {
        if (rva == SCOPE_CALL) return 1;
        return rva == SCOPE_RETURN ? 3 : 0;
    }
    if (DECODE != 0 && rva == DECODE) return 1;
    if (SCOPE_STOP != 0 && rva == SCOPE_STOP) return 3;
    return rva == GRAPH ? 2 : 0;
}
static void count(unsigned n, unsigned kind) {
    totals_t *s=drmgr_get_tls_field(dr_get_current_drcontext(),slot);
    if (!s) dr_abort();
    if (!calibration) {
        if (kind==1) { if(s->live) dr_abort(); s->live=true; }
        if (kind==3) { if(!s->live) dr_abort(); s->live=false; s->finished++; }
        if (s->live) s->inclusive+=n;
    }
    s->instructions+=n;
    s->decodes+=(kind==1);
    s->graphs+=(kind==2);
}
static dr_emit_flags_t block(void *ctx,void *tag,instrlist_t *bb,instr_t *inst,bool trace,bool translating,void *data) {
    if (!drmgr_is_first_instr(ctx,inst)) return DR_EMIT_DEFAULT;
    drmgr_disable_auto_predication(ctx,bb);
    for (instr_t *s=instrlist_first_app(bb);s;) {
        unsigned n=1,kind=marker(instr_get_app_pc(s)); instr_t *next=instr_get_next_app(s);
        while (next && !marker(instr_get_app_pc(next))) { ++n; next=instr_get_next_app(next); }
        dr_insert_clean_call(ctx,bb,s,(void *)count,false,2,OPND_CREATE_INT32(n),OPND_CREATE_INT32(kind));
        s=next;
    }
    return DR_EMIT_DEFAULT;
}
static void enter(void *ctx) {
    totals_t *s=dr_thread_alloc(ctx,sizeof(*s));memset(s,0,sizeof(*s));drmgr_set_tls_field(ctx,slot,s);
    if (kernel_pid()!=owner) return;
    dr_mutex_lock(lock);dr_fprintf(output,"T %u\n",dr_get_thread_id(ctx));dr_mutex_unlock(lock);
}
static void leave(void *ctx) {
    if (kernel_pid()!=owner) return;
    totals_t *s=drmgr_get_tls_field(ctx,slot);
    dr_mutex_lock(lock);dr_fprintf(output,"F %u %llu %llu %llu %llu %llu %u\n",dr_get_thread_id(ctx),s->instructions,s->decodes,s->graphs,s->inclusive,s->finished,s->live?1:0);dr_mutex_unlock(lock);
    dr_thread_free(ctx,s,sizeof(*s));
}
static void done(void) {
    if (kernel_pid()!=owner) return;
    dr_fprintf(output,"P %u\n",owner);dr_close_file(output);drmgr_unregister_tls_field(slot);dr_mutex_destroy(lock);drmgr_exit();
}
DR_EXPORT void dr_client_main(client_id_t id,int argc,const char *argv[]) {
    if (argc!=2 || !drmgr_init()) dr_abort();
    owner=kernel_pid();if (owner!=dr_get_process_id()) dr_abort();
    module_data_t *m=dr_get_main_module();base=m->start;
    const char *name=strrchr(m->full_path,'/');if (!name)dr_abort();
    calibration=!strcmp(name+1,"toy");scope_toy=!strcmp(name+1,"scope-toy");if(!calibration && !scope_toy && strcmp(name+1,"cargo"))dr_abort();
    output=dr_open_file(argv[1],DR_FILE_WRITE_OVERWRITE|DR_FILE_ALLOW_LARGE);
    if(output==INVALID_FILE) dr_abort();
    dr_fprintf(output,"B %u %s\n",owner,m->full_path);dr_free_module_data(m);
    lock=dr_mutex_create();slot=drmgr_register_tls_field();
    if(slot<0 || !drmgr_register_thread_init_event(enter) || !drmgr_register_thread_exit_event(leave) ||
       !drmgr_register_bb_instrumentation_event(NULL,block,NULL)) dr_abort();
    drmgr_register_exit_event(done);
}
