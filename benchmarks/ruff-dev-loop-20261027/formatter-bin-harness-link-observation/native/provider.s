.text
.globl write
.type write,@function
write:
  mov $83,%edi
  mov $231,%eax
  syscall
  ud2
.size write, .-write
.section .note.GNU-stack,"",@progbits
