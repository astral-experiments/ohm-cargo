.text
.globl _start
.type _start,@function
_start:
 leaq observed_end(%rip),%rax
 leaq observed_begin(%rip),%rdx
 sub %rdx,%rax
 xor %edi,%edi
 test %rax,%rax
 setnz %dil
 add $41,%edi
 mov $60,%eax
 syscall
.section .note.GNU-stack,"",@progbits
