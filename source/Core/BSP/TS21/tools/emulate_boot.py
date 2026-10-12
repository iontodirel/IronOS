"""Smoke-test the TS21 ELF's startup and task switching, not physical hardware.

Peripheral values and interrupt delivery are simulated. Instruction counts are
an approximate timebase, not cycle-accurate timing or a watchdog qualification.
"""

import argparse
from collections import deque
from pathlib import Path
import struct
import subprocess

from inspect_image import inspect
from unicorn import Uc, UcError, UC_ARCH_RISCV, UC_MODE_RISCV32
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.riscv_const import UC_RISCV_REG_PC, UC_RISCV_REG_X0

parser = argparse.ArgumentParser()
parser.add_argument("elf", type=Path)
parser.add_argument("--prefix", required=True)
parser.add_argument("--inherited-interrupt", action="store_true")
parser.add_argument("--instructions", type=int, default=20000000)
parser.add_argument("--max-frame-us", type=int)
args = parser.parse_args()

symbols = {}
for line in subprocess.check_output(
    [args.prefix + "nm", "-n", "-C", str(args.elf)], text=True
).splitlines():
    fields = line.split(maxsplit=2)
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)

image = args.elf.read_bytes()
inspect(image)
header = struct.unpack_from("<16sHHIIIIIHHHHHH", image)
cpu = Uc(UC_ARCH_RISCV, UC_MODE_RISCV32)
for base, length in [
    (0x08000000, 0x10000),
    (0x20000000, 0x5000),
    (0x40000000, 0x24000),
    (0xE000E000, 0x2000),
]:
    cpu.mem_map(base, length)
cpu.mem_write(0x08000000, b"\xff" * 0x10000)
for i in range(header[10]):
    kind, offset, virtual, physical, size, memsize, flags, align = struct.unpack_from(
        "<IIIIIIII", image, header[5] + i * header[9]
    )
    if kind == 1 and size:
        cpu.mem_write(physical, image[offset : offset + size])


class Board:
    def __init__(self):
        self.steps = 0
        self.csr = {}
        self.registers = {}
        self.counter = 0
        self.counter_origin = 0
        self.enabled = 0
        self.pending = 0
        self.active_irq = args.inherited_interrupt
        self.last_compare = None
        self.gpio = {0x40010800: 0, 0x40010C00: 0}
        self.i2c_active = False
        self.i2c_pulses = 0
        self.i2c_byte = 0
        self.i2c_packet = []
        self.display_bytes = 0
        self.frame_start = None
        self.frame_bytes = 0
        self.frames_us = []
        self.interrupts = {12: 0, 14: 0}
        self.last_watchdog = 0
        self.result = None
        self.recent = deque(maxlen=24)
        self.trace = {}
        for name, address in symbols.items():
            if name in (
                "main",
                "startGUITask",
                "startPIDTask",
                "startMOVTask",
                "startPOWTask",
                "xPortStartFirstTask",
                "ts21_run_constructors",
            ) or name.startswith("flash_save_buffer"):
                self.trace[address] = name
        self.seen = set()
        self.required_tasks = {
            symbols[name]
            for name in ("startGUITask", "startPIDTask", "startMOVTask", "startPOWTask")
        }
        self.instructions = {}
        text = subprocess.check_output(
            [args.prefix + "objdump", "-d", str(args.elf)], text=True
        )
        for line in text.splitlines():
            fields = line.strip().split()
            if (
                len(fields) >= 3
                and fields[0].endswith(":")
                and len(fields[1]) in (4, 8)
            ):
                try:
                    address, instruction = int(fields[0][:-1], 16), int(fields[1], 16)
                except ValueError:
                    continue
                if instruction & 0x7F == 0x73:
                    self.instructions[address] = instruction

    def now(self):
        if self.registers.get(0xE000F000, 0) & 1:
            return self.counter + (self.steps - self.counter_origin) // 8
        return self.counter

    def core_hz(self):
        clock = self.registers.get(0x40021004, 0)
        if clock & 12 == 8:
            multiplier = (clock >> 18 & 15) + 2
            if multiplier == 17:
                multiplier = 18
            source = 8000000 if self.registers.get(0x40023800, 0) & 0x10 else 4000000
            return source * multiplier
        return 8000000

    def micros(self):
        return self.now() * 8000000 // self.core_hz()

    def stop(self, reason):
        self.result = reason
        cpu.emu_stop()

    def code(self, uc, pc, size, unused):
        self.steps += 1
        self.recent.append(pc)
        if pc in self.trace and pc not in self.seen:
            self.seen.add(pc)
            print(
                f"{self.micros():8d} us {self.trace[pc]} sp={uc.reg_read(UC_RISCV_REG_X0 + 2):08x}",
                flush=True,
            )
        if pc == symbols.get("ts21_fault"):
            self.stop(
                f"FAULT error={uc.reg_read(UC_RISCV_REG_X0 + 10):x} "
                f"caller={uc.reg_read(UC_RISCV_REG_X0 + 1):08x}"
            )
            return
        instruction = self.instructions.get(pc)
        if instruction == 0x30200073:
            status = self.csr.get(0x300, 0)
            self.csr[0x300] = (status & ~0x1888) | ((status & 0x80) >> 4) | 0x80
            self.active_irq = False
            uc.reg_write(UC_RISCV_REG_PC, self.csr[0x341])
            return
        if instruction is not None and instruction >> 12 & 7:
            number, operation = instruction >> 20, instruction >> 12 & 7
            source, destination = instruction >> 15 & 31, instruction >> 7 & 31
            value = (
                source
                if operation & 4
                else uc.reg_read(UC_RISCV_REG_X0 + source) if source else 0
            )
            previous = self.csr.get(number, 0)
            mode = operation & 3
            updated = (
                value
                if mode == 1
                else previous | value if mode == 2 else previous & ~value
            )
            self.csr[number] = updated & 0xFFFFFFFF
            if destination:
                uc.reg_write(UC_RISCV_REG_X0 + destination, previous)
            uc.reg_write(UC_RISCV_REG_PC, pc + 4)
            return
        if self.registers.get(0xE000F000, 0) & 2:
            compare = (
                self.registers.get(0xE000F010, 0)
                | self.registers.get(0xE000F014, 0) << 32
            )
            if self.now() >= compare and self.last_compare != compare:
                self.last_compare = compare
                self.pending |= 1 << 12
        if not self.active_irq and self.csr.get(0x300, 0) & 8:
            ready = self.pending & self.enabled
            for irq in (12, 14):
                if ready & (1 << irq):
                    self.pending &= ~(1 << irq)
                    self.interrupts[irq] += 1
                    self.active_irq = True
                    status = self.csr[0x300]
                    self.csr[0x300] = (status & ~0x88) | ((status & 8) << 4) | 0x1800
                    self.csr[0x341] = pc
                    self.csr[0x342] = 0x80000000 | irq
                    vector = (self.csr[0x305] & ~3) + irq * 4
                    uc.reg_write(
                        UC_RISCV_REG_PC,
                        int.from_bytes(uc.mem_read(vector, 4), "little"),
                    )
                    return
        if (
            len(self.frames_us) >= 2
            and self.interrupts[12] >= 100
            and self.interrupts[14]
            and self.required_tasks <= self.seen
        ):
            if (
                args.max_frame_us is not None
                and max(self.frames_us) > args.max_frame_us
            ):
                self.stop(f"FAIL: simulated frame exceeds {args.max_frame_us} us")
            else:
                self.stop(
                    "PASS: all four tasks, two full display frames and 100 timer interrupts"
                )

    def read(self, uc, access, address, size, value, unused):
        result = self.registers.get(address, 0)
        if address == 0x40021000:
            result = (result & ~(1 << 25)) | ((result & (1 << 24)) << 1) | 2
        elif address == 0x40021004:
            result = (result & ~12) | ((result & 3) << 2)
            self.registers[address] = result
        elif address == 0x40010808:
            result = (1 << 5) | (1 << 7)
        elif address == 0x40010C08:
            result = self.gpio[0x40010C00]
            if self.i2c_active and self.i2c_pulses and self.i2c_pulses % 9 == 0:
                result &= ~(1 << 11)
        elif address == 0x40012408:
            if result & 4:
                self.registers[0x4001244C] = 1024
            result &= ~12
            self.registers[address] = result
        elif address == 0xE000F008:
            result = self.now() & 0xFFFFFFFF
        elif address == 0xE000F00C:
            result = self.now() >> 32
        uc.mem_write(address, int(result).to_bytes(size, "little"))

    def write(self, uc, access, address, size, value, unused):
        self.registers[address] = value
        if address in (0x40010810, 0x40010814, 0x40010C10, 0x40010C14):
            base = address & ~0xFF
            old = self.gpio[base]
            new = old | value if address & 0xFF == 0x10 else old & ~value
            self.gpio[base] = new
            if base == 0x40010800 and new & ((1 << 6) | (1 << 10)):
                self.stop("FAIL: heater pin driven high")
            if base == 0x40010C00:
                scl, sda = 1 << 10, 1 << 11
                if old & scl and new & scl:
                    if old & sda and not new & sda:
                        self.i2c_active = True
                        self.i2c_pulses = self.i2c_byte = 0
                        self.i2c_packet = []
                    elif not old & sda and new & sda:
                        self.i2c_active = False
                        if self.i2c_packet == [0x78, 0x00, 0xB0]:
                            self.frame_start = self.micros()
                            self.frame_bytes = 0
                        if self.i2c_packet[:2] == [0x78, 0x40]:
                            count = len(self.i2c_packet) - 2
                            self.display_bytes += count
                            self.frame_bytes += count
                            if self.frame_start is not None and self.frame_bytes == 512:
                                self.frames_us.append(self.micros() - self.frame_start)
                                self.frame_start = None
                if self.i2c_active and not old & scl and new & scl:
                    self.i2c_pulses += 1
                    if self.i2c_pulses % 9:
                        self.i2c_byte = (self.i2c_byte << 1) | bool(new & sda)
                    else:
                        self.i2c_packet.append(self.i2c_byte)
                        self.i2c_byte = 0
        elif address == 0x40012408 and value & 0x400000:
            channel = self.registers.get(0x40012434)
            self.registers[0x40012400] = 2
            self.registers[0x4001244C] = {1: 580, 2: 2000, 4: 100, 9: 725}[channel]
        elif address == 0x4002200C:
            self.registers[address] = 0
        elif address == 0x40022010 and value & 0x20040 == 0x20040:
            target = self.registers[0x40022014]
            if target != 0x0800FC00:
                self.stop(f"FAIL: unexpected flash erase at {target:08x}")
            uc.mem_write(target, b"\xff" * 256)
        elif address == 0xE000E100:
            self.enabled |= value
        elif address == 0xE000E180:
            self.enabled &= ~value
        elif address == 0xE000E200:
            self.pending |= value
        elif address == 0xE000E280:
            self.pending &= ~value
        elif address in (0xE000F008, 0xE000F00C):
            self.counter = (
                self.registers.get(0xE000F008, 0)
                | self.registers.get(0xE000F00C, 0) << 32
            )
            self.counter_origin = self.steps
        elif address == 0x40003000:
            self.last_watchdog = self.micros()
        elif address == 0xE000E048 and value == 0xBEEF0080:
            self.stop("FAIL: firmware requested reset")


board = Board()
cpu.hook_add(UC_HOOK_CODE, board.code)
for start, end in [(0x40000000, 0x40023FFF), (0xE000E000, 0xE000FFFF)]:
    cpu.hook_add(UC_HOOK_MEM_READ, board.read, begin=start, end=end)
    cpu.hook_add(UC_HOOK_MEM_WRITE, board.write, begin=start, end=end)
try:
    cpu.emu_start(header[4], 0, count=args.instructions)
except UcError as error:
    board.result = f"EMULATION ERROR: {error}, PC={cpu.reg_read(UC_RISCV_REG_PC):08x}"
print(board.result or "FAIL: instruction budget exhausted", flush=True)
print(
    f"steps={board.steps}, us={board.micros()}, core_hz={board.core_hz()}, "
    f"IRQ={board.interrupts}, display_bytes={board.display_bytes}, frame_us={board.frames_us}, "
    f"watchdog_gap_us={board.micros() - board.last_watchdog}, CSRs={board.csr}",
    flush=True,
)
print("recent PCs: " + " ".join(f"{pc:08x}" for pc in board.recent), flush=True)
raise SystemExit(0 if board.result and board.result.startswith("PASS") else 1)
