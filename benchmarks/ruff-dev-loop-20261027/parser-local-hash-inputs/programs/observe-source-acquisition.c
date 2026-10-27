#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* A read-only probe for the fixed x86_64 #233 release. The GOT caller's
 * instruction offsets and its stack layout are separately verified with objdump. */
#define ENTRY _RNvMs_CslwfoDbT1Q2U_10rustc_spanNtB4_15MetavarSpansMap25freeze_and_get_read_spans
#define STR1(x) #x
#define STR(x) STR1(x)
typedef void* (*freeze_fn)(void *, const void *);
void *ENTRY(void *dst, const void *state) {
    void *ret = __builtin_return_address(0);
    Dl_info info;
    const char *path = getenv("OHM_SCOUT_SPAN_LOG");
    freeze_fn real = (freeze_fn)dlsym(RTLD_NEXT, STR(ENTRY));
    if (!real) _exit(106);
    if (!path || !dladdr(ret,&info) || (uintptr_t)ret-(uintptr_t)info.dli_fbase != 0x5d8407f)
        return real(dst,state);
    uint64_t buffered, processed;
    unsigned char data[64], sip[32];
    const unsigned char *hasher=(unsigned char*)dst-0x78;
    memcpy(&buffered,hasher,sizeof(buffered));
    if (buffered>=sizeof(data)) _exit(107);
    memcpy(data,hasher+8,buffered);
    memcpy(sip,hasher+80,32);
    memcpy(&processed,hasher+112,sizeof(processed));

    /* The x86_64 code stores this Vec pointer and length in these caller
     * slots before hashing. Its allocation remains live until the end of the provider. */
    const unsigned char *base = (const unsigned char *)dst - 0x138;
    unsigned char *ids;
    size_t names;
    memcpy(&ids,base+0x28,sizeof(ids));
    memcpy(&names,base+0x258,sizeof(names));
    if (!ids || !names || names>512) _exit(116);
    const char *sort_log = getenv("OHM_SCOUT_FILE_SORT_LOG");
    FILE *files = sort_log ? fopen(sort_log,"a") : NULL;
    if (!files) _exit(117);
    fprintf(files,"{\"return_offset\":\"5d8407f\",\"entries\":%zu,\"stable_source_ids_le\":[",names);
    for(size_t i=0;i<names;i++){
        if(i) fputc(',',files);
        fputc('"',files);
        for(size_t j=0;j<16;j++) fprintf(files,"%02x",ids[i*16+j]);
        fputc('"',files);
    }
    if(fputs("]}\n",files)<0 || fclose(files)) _exit(118);
    void *answer=real(dst,state);
    uint64_t entries;
    memcpy(&entries,(unsigned char*)dst+24,8);
    char line[800]; int n=snprintf(line,sizeof(line),"{\"return_offset\":\"5d8407f\",\"buffered\":%"PRIu64",\"processed\":%"PRIu64",\"used_buffer_hex\":\"",buffered,processed);
    for(size_t i=0;i<buffered;i++)n+=snprintf(line+n,sizeof(line)-n,"%02x",data[i]);
    n+=snprintf(line+n,sizeof(line)-n,"\",\"sip_state_hex\":\"");
    for(size_t i=0;i<32;i++)n+=snprintf(line+n,sizeof(line)-n,"%02x",sip[i]);
    n+=snprintf(line+n,sizeof(line)-n,"\",\"frozen_map_entries\":%"PRIu64"}\n",entries);
    int fd=open(path,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0600);
    if(fd<0 || write(fd,line,n)!=n || close(fd)<0) _exit(108);
    return answer;
}

#include <execinfo.h>
#define LOOKUP _RNvMs1_NtCslwfoDbT1Q2U_10rustc_span10source_mapNtB5_9SourceMap24source_file_by_stable_id
/* Fixed ELF: new_source_file puts &FileName in rbx and &String in r13
 * before the lookup at 6a0382f. The shim captures them without modifying
 * the three true arguments or the return address. */
__asm__(".text\n.globl " STR(LOOKUP) "\n.type " STR(LOOKUP) ",@function\n" STR(LOOKUP) ":\n"
    "movq %rbx,%rcx\nmovq %r13,%r8\nmovq (%rsp),%r9\njmp scout_lookup\n");
__attribute__((visibility("hidden"))) void *scout_lookup(void *map,uint64_t lo,uint64_t hi,const unsigned char *name,const unsigned char *src,void *ret) {
    typedef void *(*lookup_fn)(void*,uint64_t,uint64_t);
    lookup_fn real=(lookup_fn)dlsym(RTLD_NEXT,STR(LOOKUP));
    if(!real) _exit(121);
    Dl_info caller;
    const char *path=getenv("OHM_SCOUT_ACQUIRE_LOG");
    if(!path || !dladdr(ret,&caller) || (uintptr_t)ret-(uintptr_t)caller.dli_fbase!=0x6a03835) return real(map,lo,hi);
    size_t n; const unsigned char *s; uint64_t tag;
    memcpy(&s,src+8,8);memcpy(&n,src+16,8);memcpy(&tag,name,8);
    if(n>64*1024*1024 || (n && !s)) _exit(122);
    uint64_t hash=UINT64_C(14695981039346656037);
    for(size_t i=0;i<n;i++) hash=(hash^s[i])*UINT64_C(1099511628211);
    const unsigned char *p=(const unsigned char *)&lo,*q=(const unsigned char *)&hi;
    uint64_t kind=(int64_t)tag<0 ? tag+UINT64_C(0x8000000000000001) : 0;
    char line[7000];
    int x=snprintf(line,sizeof(line),"{\"id\":\"");
    for(int i=0;i<8;i++) x+=snprintf(line+x,sizeof(line)-x,"%02x",p[i]);
    for(int i=0;i<8;i++) x+=snprintf(line+x,sizeof(line)-x,"%02x",q[i]);
    x+=snprintf(line+x,sizeof(line)-x,"\",\"length\":%zu,\"fnv64\":\"%016"PRIx64"\",\"file_name_tag\":%"PRIu64,n,hash,kind);
    if(lo==UINT64_C(0xd22d5d3d2a467541) && hi==UINT64_C(0x639c3af16ad222d4)) {
        x+=snprintf(line+x,sizeof(line)-x,",\"prefix_hex\":\"");
        for(size_t i=0;i<n && i<100;i++) x+=snprintf(line+x,sizeof(line)-x,"%02x",s[i]);
        x+=snprintf(line+x,sizeof(line)-x,"\",\"frames\":[");
        void *frames[48];int k=backtrace(frames,48);
        for(int i=0;i<k;i++) {
            Dl_info d; const char *img="unknown"; uintptr_t pc=0;
            if(dladdr(frames[i],&d)) { img=strrchr(d.dli_fname,'/'); img=img?img+1:d.dli_fname;pc=(uintptr_t)frames[i]-(uintptr_t)d.dli_fbase; }
            if(strlen(img)>120) _exit(123);
            x+=snprintf(line+x,sizeof(line)-x,"%s[\"%s\",\"%"PRIxPTR"\"]",i?",":"",img,pc);
        }
        x+=snprintf(line+x,sizeof(line)-x,"]");
    }
    x+=snprintf(line+x,sizeof(line)-x,"}\n");
    int fd=open(path,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0600);if(fd<0 || write(fd,line,x)!=x || close(fd)) _exit(124);
    return real(map,lo,hi);
}
