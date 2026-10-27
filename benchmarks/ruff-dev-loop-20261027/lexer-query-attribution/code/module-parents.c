/* Read a rustc dep-graph, retaining only exactly keyed lex, lexer module and parser root nodes.
 * Format: current query-system SerializedDepGraph writer and previously calibrated probe-graph.c. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <assert.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
static uint64_t u64(const unsigned char *p){uint64_t x;memcpy(&x,p,8);return x;}
static uint32_t u32(const unsigned char *p){uint32_t x;memcpy(&x,p,4);return x;}
static uint16_t u16(const unsigned char *p){uint16_t x;memcpy(&x,p,2);return x;}
static unsigned leb(const unsigned char **p){unsigned v=0,b;for(unsigned i=0;i<=28;i+=7){b=*(*p)++;v|=(b&127)<<i;if(b<128)return v;}abort();}
int main(int argc,char **argv){
 assert(argc==6);int fd=open(argv[1],O_RDONLY|O_NOFOLLOW|O_NONBLOCK);assert(fd>=0);
 uint64_t crate=strtoull(argv[2],NULL,16), lex=strtoull(argv[3],NULL,16), module=strtoull(argv[4],NULL,16);
 struct stat st;assert(fstat(fd,&st)==0&&S_ISREG(st.st_mode));unsigned char *b=mmap(0,st.st_size,PROT_READ,MAP_PRIVATE,fd,0);assert(b!=MAP_FAILED);
 const unsigned char *end=b+st.st_size,*f=end-61;assert(!memcmp(end-13,"rust-end-file",13));
 uint64_t total_nodes=u64(f+32),max_idx=u64(f+24),tot_edges=u64(f+40),edges=0,matches=0,parserkeys=0;assert(total_nodes<=max_idx&&max_idx<20000000);
 const unsigned char *start=b+7+b[6]+8,*p=start,*md=NULL;
 unsigned short *target=calloc(max_idx,sizeof(*target));assert(target);
 /* A nonzero target ID encodes one of the three known DefPathHashes plus its DefKind. */
 for(size_t i=0;i<total_nodes;i++){
  assert(p+38<=end);unsigned hd=u16(p),kind=hd&511,ix=u32(p+2),width=1+((hd>>9)&3);assert(ix<max_idx);
  if(kind==7){assert(!md&&!u64(p+6)&&!u64(p+14));md=p;}
  if(u64(p+6)==crate){
   parserkeys++;uint64_t lo=u64(p+14);unsigned slot=lo==lex?1:lo==module?2:lo==crate?3:0;
   if(slot){
    target[ix]=slot*512+kind;matches++;printf("q %u %u ",slot,kind);
    for(unsigned j=0;j<16;j++)printf("%02x",p[22+j]);
    putchar('\n');
   }
  }
  p+=38;unsigned n=hd>>11;n=n?n-1:leb(&p);edges+=n;p+=(size_t)n*width;
 }
 assert(edges==tot_edges);printf("t %lu %lu %lu %lu %u\n",total_nodes,edges,parserkeys,matches,md!=NULL);
 if(md){
  unsigned hd=u16(md),width=1+((hd>>9)&3),n=hd>>11;p=md+38;n=n?n-1:leb(&p);
  for(unsigned i=0;i<n;i++,p+=width){
   unsigned ix=0;memcpy(&ix,p,width);assert(ix<max_idx);
   if(target[ix])printf("m %u %u\n",target[ix]/512,target[ix]%512);
  }
 }

 unsigned wanted_lexer=2*512+strtoul(argv[5],NULL,10);
 p=start;
 for(size_t i=0;i<total_nodes;i++){
  const unsigned char *node=p; unsigned hd=u16(p),width=1+((hd>>9)&3),n=hd>>11;
  p+=38;n=n?n-1:leb(&p);
  for(unsigned j=0;j<n;j++,p+=width){
   unsigned ix=0;memcpy(&ix,p,width);assert(ix<max_idx);
   if(target[ix]==wanted_lexer){
    printf("input_to %u %016lx %016lx ",hd&511,u64(node+6),u64(node+14));
    for(unsigned k=0;k<16;k++)printf("%02x",node[22+k]);putchar(10);
   }
  }
 }
 free(target);munmap(b,st.st_size);close(fd);
}
