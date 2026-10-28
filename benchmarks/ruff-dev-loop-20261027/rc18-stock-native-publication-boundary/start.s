.text
.global _start
_start:
 mov ordinary(%rip),%edi
 add eight(%rip),%edi
 mov $60,%eax
 syscall
.section .note.GNU-stack,"",@progbits
