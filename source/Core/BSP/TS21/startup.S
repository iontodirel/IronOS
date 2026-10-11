    .section .init, "ax", @progbits
    .global _start
    .option push
    .option norvc
_start:
    j reset_handler
    .option pop

    .section .vectors, "a", @progbits
    .balign 4
    .global vector_base
vector_base:
    .word _start
    .rept 63
    .word fault_handler
    .endr

    .section .text.startup, "ax", @progbits
    .balign 4
reset_handler:
    csrw mstatus, zero
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, __stack_top
    la t0, __data_load
    la t1, __data_start
    la t2, __data_end
1:
    bgeu t1, t2, 2f
    lw t3, 0(t0)
    sw t3, 0(t1)
    addi t0, t0, 4
    addi t1, t1, 4
    j 1b
2:
    la t1, __bss_start
    la t2, __bss_end
3:
    bgeu t1, t2, 4f
    sw zero, 0(t1)
    addi t1, t1, 4
    j 3b
4:
    csrw 0x804, zero
    la t0, vector_base
    ori t0, t0, 3
    csrw mtvec, t0
    call main
fault_handler:
    csrw mstatus, zero
    li a0, 64
    tail ts21_fault
