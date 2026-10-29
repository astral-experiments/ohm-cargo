.text
.globl scope_one,suffix_call,suffix_return
.type scope_one,@function
scope_one:
suffix_call:
 call fixture_loop
suffix_return:
 ret
.type fixture_loop,@function
fixture_loop:
 mov %edi,%ecx
 xor %eax,%eax
1:
 inc %eax
 dec %ecx
 jne 1b
 ret
.section .note.GNU-stack,"",@progbits
