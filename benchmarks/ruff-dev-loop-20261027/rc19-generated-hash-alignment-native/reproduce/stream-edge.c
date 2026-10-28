#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
static struct stat target;
static const char *mode,*path;
static unsigned reads;
__attribute__((constructor))static void setup(void){mode=getenv("EDGE_MODE");path=getenv("EDGE_FILE");if(!mode||!path||stat(path,&target))_exit(71);}
ssize_t read(int fd,void *buf,size_t len){struct stat s;
 if(fstat(fd,&s)||!mode||s.st_ino!=target.st_ino||s.st_dev!=target.st_dev)return syscall(SYS_read,fd,buf,len);
 if(reads==1&&!strcmp(mode,"eio")){errno=EIO;return -1;}
 if(reads==1&&!strcmp(mode,"eintr")){errno=EINTR;return -1;}
 size_t limit=reads==0?37:317;ssize_t n=syscall(SYS_read,fd,buf,len<limit?len:limit);
 if(n>0&&reads++==0&&(!strcmp(mode,"grow")||!strcmp(mode,"shrink"))){int w=syscall(SYS_openat,AT_FDCWD,path,O_WRONLY|O_APPEND|O_CLOEXEC);if(w<0)_exit(72);
  if(!strcmp(mode,"grow")){unsigned char tail[1547];memset(tail,7,sizeof(tail));if(syscall(SYS_write,w,tail,sizeof(tail))!=sizeof(tail))_exit(73);}
  else if(ftruncate(w,53))_exit(74);syscall(SYS_close,w);
 }return n;
}
