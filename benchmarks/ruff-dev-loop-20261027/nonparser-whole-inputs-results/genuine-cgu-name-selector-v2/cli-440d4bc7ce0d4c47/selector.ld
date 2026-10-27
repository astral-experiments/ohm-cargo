ENTRY(_start)
SECTIONS {
 . = 0x600000;
 .text : { *(.text._start) }
 .selected : { picked_start = .; KEEP(*cli-440d4bc7ce0d4c47.00xnreyn3fq67vg1cparhvqty.1nqw4d8.rcgu.o(.rodata..Lanon.331294c65abf46db297232e03b152236.11)) picked_end = .; }
 .rest : { KEEP(*(.rodata..Lanon.331294c65abf46db297232e03b152236.11)) }
 /DISCARD/ : { *(*) }
}
