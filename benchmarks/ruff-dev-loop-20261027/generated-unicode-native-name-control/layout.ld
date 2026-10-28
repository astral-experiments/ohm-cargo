ENTRY(_start)
SECTIONS {
 . = 0x600000;
 .selected : { picked_start = .; KEEP(unicode_names2-2d5a69c08d8660d3.alhk5wm1ntvbjem57v93ifhqs.196ze60.rcgu.o(.text._RNvCs6tuOZN82rAq_14unicode_names24name)) picked_end = .; }
 .text : { *(.text*) }
 .rodata : { *(.rodata*) }
 . = ALIGN(4096);
 .data : { *(.data*) }
 .bss : { *(.bss*) }
}
