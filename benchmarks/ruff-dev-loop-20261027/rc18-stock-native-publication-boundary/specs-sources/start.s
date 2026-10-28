.global _start
.text
_start:
call auditffi
mov %eax,%edi
mov $60,%eax
syscall
