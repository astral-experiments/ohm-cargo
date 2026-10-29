#include <unistd.h>
#include <sys/wait.h>
#include <string.h>
int main(void) {
    char *message = "{\"$message_type\":\"unused_externs\",\"unused_extern_names\":[\"known_unused\"]}\n";
    if (write(2, message, strlen(message)) != (ssize_t)strlen(message)) return 1;
    pid_t child=fork();
    if(child==0){execlp("cc","cc","--version",NULL);_exit(127);}
    int s=0;if(waitpid(child,&s,0)!=child)return 2;
    return WIFEXITED(s)?WEXITSTATUS(s):3;
}
