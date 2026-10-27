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
