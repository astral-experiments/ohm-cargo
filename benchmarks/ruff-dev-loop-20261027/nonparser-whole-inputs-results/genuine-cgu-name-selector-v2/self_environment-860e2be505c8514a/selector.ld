ENTRY(_start)
SECTIONS {
 . = 0x600000;
 .text : { *(.text._start) }
 .selected : { picked_start = .; KEEP(*self_environment-860e2be505c8514a.1wk2ac24at111atbwzggyc0f5.0zo90dx.rcgu.o(.rodata..Lanon.89ebf69019ef0b61ee4b8a0dbd752073.23)) picked_end = .; }
 .rest : { KEEP(*(.rodata..Lanon.89ebf69019ef0b61ee4b8a0dbd752073.23)) }
 /DISCARD/ : { *(*) }
}
