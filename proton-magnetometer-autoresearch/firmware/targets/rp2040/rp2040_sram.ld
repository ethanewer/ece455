/* SRAM-resident link for the rp2040js plumbing check (no flash, no
 * boot2): the emulator loads the image at its link address and starts
 * the core from the vector table's SP/PC. */
ENTRY(firmware_main)

MEMORY
{
    SRAM (rwx) : ORIGIN = 0x20000000, LENGTH = 256K
}

SECTIONS
{
    . = 0x20000000;
    .vectors : { KEEP(*(.vectors)) } > SRAM
    .text : { *(.text*) *(.rodata*) } > SRAM
    .data : { *(.data*) } > SRAM
    .bss : { *(.bss*) *(COMMON) } > SRAM
}
