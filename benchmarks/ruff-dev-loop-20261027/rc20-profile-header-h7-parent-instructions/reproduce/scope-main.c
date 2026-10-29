#include <stdlib.h>
extern int scope_one(int);
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    int n=atoi(argv[1]);
    return n<=0 || scope_one(n)!=n;
}
