ENTRY(_start)
SECTIONS { . = 0x600000; .selected : { observed_begin = .; KEEP(ruff_formatter-ec58abd591816f64.c3zqw3xtta3zlit01ggeetfg9.0tkbpa2.rcgu.o(.text._RNvXNtCs5G1tBLHbvoM_14ruff_formatter11diagnosticsNtB2_11FormatErrorNtNtCs7EQkTZ5ohTs_4core3fmt7Display3fmt)) observed_end = .; } .text : { *(.text*) } .rodata : { *(.rodata*) } . = ALIGN(4096); .data : { *(.data*) } .bss : { *(.bss*) } }
