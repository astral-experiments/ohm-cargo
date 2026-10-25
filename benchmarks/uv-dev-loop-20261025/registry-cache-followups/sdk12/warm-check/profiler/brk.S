        .section .text
        .globl _start
        .type _start,@function
_start:
        xor %edi, %edi
        mov $12, %eax
        syscall
        lea REQUEST_BYTES(%rax), %rdi
        mov %rdi, %r12
        mov $12, %eax
        syscall
        mov $77, %edi
        cmp %r12, %rax
        jne .Lexit
        movb $0x5a, -1(%r12)
        xor %edi, %edi
.Lexit:
        mov $60, %eax
        syscall
        .size _start, .-_start
        .section .note.GNU-stack,"",@progbits
