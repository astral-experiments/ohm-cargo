#define _GNU_SOURCE
#include "blake3.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

struct proof {size_t len; unsigned char *bytes; unsigned char raw[32];};
static unsigned char second_digest[3][32],tree_digest[2][32];
static uint64_t read_bytes,retained,peak;
static int misses;
static void fail(const char *msg){perror(msg);exit(61);}
static uint64_t now(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t))fail("clock");return ((uint64_t)t.tv_sec)*1000000000+t.tv_nsec;}
static int open_input(const char *path,struct stat *st){
 int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0||fstat(fd,st))fail("operand");
 if(!S_ISREG(st->st_mode)||st->st_size<=0||st->st_size>16*1024*1024)exit(62);return fd;
}
static void first(const char *path,int copy,struct proof *p,blake3_hasher *tree){
 struct stat st;int fd=open_input(path,&st);p->len=st.st_size;
 const char *base=strrchr(path,'/');if(!base)exit(63);base++;
 blake3_hasher_update(tree,base,strlen(base));blake3_hasher_update(tree,&p->len,sizeof(p->len));
 unsigned char buf[16384];blake3_hasher leaf;size_t at=0;
 if(copy){p->bytes=malloc(p->len);if(!p->bytes)fail("copy");retained+=p->len;if(retained>peak)peak=retained;blake3_hasher_init(&leaf);}
 for(;;){unsigned char *dst=(!copy||at>=p->len)?buf:p->bytes+at;size_t room=copy&&at<p->len&&p->len-at<sizeof(buf)?p->len-at:sizeof(buf);
  ssize_t n=read(fd,dst,room);if(n<0)fail("read1");if(n==0)break;
  if(at+(size_t)n>p->len)exit(64);
  blake3_hasher_update(copy?&leaf:tree,dst,n);at+=n;read_bytes+=n;}
 if(at!=p->len||close(fd))exit(65);
 if(copy){blake3_hasher_finalize(&leaf,p->raw,32);blake3_hasher_update(tree,p->raw,32);}
}
static void second(const char *path,int copy,struct proof *p,unsigned char digest[32]){
 struct stat st;int fd=open_input(path,&st);unsigned char buf[65536];size_t at=0;int equal=copy;
 blake3_hasher raw;if(!equal)blake3_hasher_init(&raw);
 for(;;){ssize_t n=read(fd,buf,sizeof(buf));if(n<0)fail("read2");if(n==0)break;
  if(equal&&(at+(size_t)n>p->len||memcmp(p->bytes+at,buf,(size_t)n))){blake3_hasher_init(&raw);blake3_hasher_update(&raw,p->bytes,at);equal=0;misses++;}
  if(!equal)blake3_hasher_update(&raw,buf,(size_t)n);at+=n;read_bytes+=n;}
 if(equal&&at!=p->len){blake3_hasher_init(&raw);blake3_hasher_update(&raw,p->bytes,at);equal=0;misses++;}
 if(equal)memcpy(digest,p->raw,32);else blake3_hasher_finalize(&raw,digest,32);
 if(close(fd))fail("close");if(copy){free(p->bytes);retained-=p->len;}
}
static void hex(const unsigned char *raw){for(int i=0;i<32;i++)printf("%02x",raw[i]);}
int main(int argc,char **argv){
 if(argc!=6)return 60;int copy=strcmp(argv[1],"copy")==0;struct proof proofs[3]={{0}};
 struct rusage u,v;getrusage(RUSAGE_SELF,&u);uint64_t start=now();
 for(int group=0;group<2;group++){int begin=group?2:0,end=group?3:2;blake3_hasher tree;blake3_hasher_init(&tree);
  for(int i=begin;i<end;i++) first(argv[i+2],copy,&proofs[i],&tree);
  blake3_hasher_finalize(&tree,tree_digest[group],32);
  for(int i=begin;i<end;i++)second(i==2?argv[5]:argv[i+2],copy,&proofs[i],second_digest[i]);
 }
 uint64_t duration=now()-start;getrusage(RUSAGE_SELF,&v);
 printf("{\"ns\":%"PRIu64",\"minflt\":%ld,\"read_bytes\":%"PRIu64",\"peak_saved_bytes\":%"PRIu64",\"copy_misses\":%d,\"raw_blake3\":[",duration,v.ru_minflt-u.ru_minflt,read_bytes,peak,misses);
 for(int i=0;i<3;i++){printf(i?",\"":"\"");hex(second_digest[i]);printf("\"");}
 printf("],\"model_tree\":[\"");hex(tree_digest[0]);printf("\",\"");hex(tree_digest[1]);puts("\"]}");return 0;
}
