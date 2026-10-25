        .section .text
        .globl _start
        .type _start,@function
_start:
        mov $ITERATIONS, %ecx
        xor %edi, %edi
.Lloop:
        add $1, %edi
        dec %ecx
        jnz .Lloop
        mov $60, %eax
        xor %edi, %edi
        syscall
        .size _start, .-_start
        .section .note.GNU-stack,"",@progbits
