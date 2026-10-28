#include "dr_api.h"
#include "drmgr.h"
#include "drwrap.h"
#include <stdint.h>
#include <string.h>
typedef struct { unsigned depth[8],mask; uint64_t bins[256]; } local_t;
static int idx;static void *lock;static file_t out;static unsigned installed;
static const uintptr_t offsets[]={0x86b220,0x7e1b10,0x9c7700,0x8a6240,0x7e2ec0,0x86d4f0,0x16e3800,0x16e3440};
static local_t* get(void){return drmgr_get_tls_field(dr_get_current_drcontext(),idx);}
static void enter(void *wrapcxt,void **user_data){(void)wrapcxt; unsigned n=(unsigned)(uintptr_t)*user_data;local_t *s=get();if(!s||n>=8)dr_abort();if(!s->depth[n]++)s->mask|=1u<<n;}
static void leave(void *wrapcxt,void *user_data){(void)wrapcxt;unsigned n=(unsigned)(uintptr_t)user_data;local_t *s=get();if(!s||n>=8||!s->depth[n])dr_abort();if(!--s->depth[n])s->mask&=~(1u<<n);}
static void module(void *ctx,const module_data_t *m,bool prior){
    const char *n=dr_module_preferred_name(m);if(!n||strcmp(n,"cargo"))return;
    if(installed++)dr_abort();
    for(unsigned i=0;i<8;i++)if(!drwrap_wrap_ex(m->start+offsets[i],enter,leave,(void*)(uintptr_t)i,0))dr_abort();
    dr_fprintf(out,"M %p %s\n",m->start,m->full_path);
}
static void tstart(void *ctx){local_t *s=dr_thread_alloc(ctx,sizeof(*s));memset(s,0,sizeof(*s));drmgr_set_tls_field(ctx,idx,s);dr_mutex_lock(lock);dr_fprintf(out,"T %u\n",dr_get_thread_id(ctx));dr_mutex_unlock(lock);}
static void tend(void *ctx){local_t *s=drmgr_get_tls_field(ctx,idx);if(!s)dr_abort();dr_mutex_lock(lock);
 for(unsigned i=0;i<256;i++)if(s->bins[i])dr_fprintf(out,"I %u %u %llu\n",dr_get_thread_id(ctx),i,(unsigned long long)s->bins[i]);
 dr_fprintf(out,"F %u %u\n",dr_get_thread_id(ctx),s->mask);dr_mutex_unlock(lock);dr_thread_free(ctx,s,sizeof(*s));}
static void tally(ptr_uint_t n){local_t *s=get();if(!s)dr_abort();s->bins[s->mask]+=n;}
static dr_emit_flags_t bb(void *ctx,void *tag,instrlist_t *list,instr_t *inst,bool trace,bool translating,void *extra){
 if(!drmgr_is_first_instr(ctx,inst))return DR_EMIT_DEFAULT;unsigned n=0;for(instr_t *i=instrlist_first_app(list);i;i=instr_get_next_app(i))n++;
 dr_insert_clean_call(ctx,list,inst,(void*)tally,false,1,OPND_CREATE_INTPTR(n));return DR_EMIT_DEFAULT;
}
static void done(void){dr_fprintf(out,"E %u %u\n",dr_get_process_id(),installed);dr_close_file(out);dr_mutex_destroy(lock);drwrap_exit();drmgr_exit();}
DR_EXPORT void dr_client_main(client_id_t id,int argc,const char *argv[]){
 if(argc!=2||!drmgr_init()||!drwrap_init())dr_abort();idx=drmgr_register_tls_field();if(idx<0)dr_abort();lock=dr_mutex_create();out=dr_open_file(argv[1],DR_FILE_WRITE_OVERWRITE);if(out==INVALID_FILE)dr_abort();
 dr_fprintf(out,"B %u\n",dr_get_process_id());drmgr_register_thread_init_event(tstart);drmgr_register_thread_exit_event(tend);
 drmgr_register_module_load_event(module);drmgr_register_exit_event(done);
 if(!drmgr_register_bb_instrumentation_event(NULL,bb,NULL))dr_abort();
}
