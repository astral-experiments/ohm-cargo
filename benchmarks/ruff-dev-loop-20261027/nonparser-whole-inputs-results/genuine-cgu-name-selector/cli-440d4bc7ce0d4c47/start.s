.section .text._start,"ax",@progbits
.global _start
_start:
  leaq picked_end(%rip), %rdi
  leaq picked_start(%rip), %rax
  subq %rax, %rdi
  movl $60, %eax
  syscall
.section .note.GNU-stack,"",@progbits
