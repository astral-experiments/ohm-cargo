.text
.local ohm_native_provider_exit_83
.type ohm_native_provider_exit_83,@function
ohm_native_provider_exit_83:
 mov $231,%eax
 mov $83,%edi
 syscall
 ud2
.size ohm_native_provider_exit_83,.-ohm_native_provider_exit_83
.section .init_array,"aw",@init_array
.p2align 3
.quad ohm_native_provider_exit_83
.section .note.GNU-stack,"",@progbits
