.text
.global _start
.type _start,@function
_start:
  leaq picked_end(%rip),%rax
  leaq picked_start(%rip),%rdx
  subq %rdx,%rax
  xor %edi,%edi
  test %rax,%rax
  setnz %dil
  addl $41,%edi
  mov $60,%eax
  syscall
.section .note.GNU-stack,"",@progbits
