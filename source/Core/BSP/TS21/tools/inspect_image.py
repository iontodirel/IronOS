"""Check a TS21 diagnostic ELF's layout, not its hardware compatibility."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


APP_START = 0x08007000
FLASH_END = 0x0800FC00
RAM_START = 0x20000000
STACK_BOTTOM = 0x20004800
VECTOR_BASE = APP_START + 4
VECTOR_COUNT = 64
ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIIIIIII")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def inspect(data: bytes) -> dict:
    require(len(data) >= ELF_HEADER.size, "Truncated ELF header")
    header = ELF_HEADER.unpack_from(data)
    (
        ident,
        kind,
        machine,
        version,
        entry,
        phoff,
        _shoff,
        flags,
        ehsize,
        phentsize,
        phnum,
        _shentsize,
        _shnum,
        _shstrndx,
    ) = header
    require(ident[:7] == b"\x7fELF\x01\x01\x01", "Expected little-endian ELF32")
    require(
        kind == 2 and machine == 243 and version == 1,
        "Expected an executable RISC-V ELF",
    )
    require(flags & 0xE == 0, "Expected full-register, soft-float RV32 ABI")
    require(ehsize == ELF_HEADER.size, "Unexpected ELF header size")
    require(entry == APP_START, "Entry point must preserve the 28 KiB bootloader")
    require(
        phentsize == PROGRAM_HEADER.size and phnum > 0, "Invalid program header table"
    )
    require(
        phoff >= ehsize and phoff + phnum * phentsize <= len(data),
        "Truncated program header table",
    )

    flash_segments = []
    ram_ranges = []
    executable_ranges = []
    for index in range(phnum):
        segment = PROGRAM_HEADER.unpack_from(data, phoff + index * phentsize)
        ptype, offset, vaddr, paddr, filesz, memsz, permissions, alignment = segment
        if ptype != 1:
            continue
        require(filesz <= memsz, "Segment file size exceeds memory size")
        require(offset + filesz <= len(data), "Segment extends past the input file")
        require(
            alignment in (0, 1) or alignment & (alignment - 1) == 0,
            "Invalid segment alignment",
        )
        if alignment > 1:
            require(offset % alignment == vaddr % alignment, "Misaligned load segment")
        if RAM_START <= vaddr < STACK_BOTTOM:
            require(
                vaddr + memsz <= STACK_BOTTOM, "RAM overlaps the reserved 2 KiB stack"
            )
            ram_ranges.append((vaddr, vaddr + memsz))
        else:
            require(
                APP_START <= vaddr and vaddr + memsz <= FLASH_END,
                "Virtual load address is outside application flash/RAM",
            )
        if filesz:
            require(
                APP_START <= paddr and paddr + filesz <= FLASH_END,
                "Image overwrites bootloader or persistent settings",
            )
            flash_segments.append((paddr, paddr + filesz, offset))
        if permissions & 1:
            require(
                APP_START <= vaddr and vaddr + filesz <= FLASH_END,
                "Executable segment is not in application flash",
            )
            require(
                vaddr == paddr, "Executable segment has a different physical address"
            )
            executable_ranges.append((vaddr, vaddr + filesz))

    require(
        bool(flash_segments) and bool(executable_ranges),
        "Missing executable flash contents",
    )
    for ranges in (flash_segments, ram_ranges):
        ordered = sorted(ranges)
        for previous, current in zip(ordered, ordered[1:]):
            require(previous[1] <= current[0], "Overlapping load segments")

    def flash_word(address: int) -> int:
        for start, end, offset in flash_segments:
            if start <= address and address + 4 <= end:
                return struct.unpack_from("<I", data, offset + address - start)[0]
        raise ValueError(f"Missing flash word at 0x{address:08X}")

    def executable(address: int) -> bool:
        return address % 2 == 0 and any(
            start <= address and address + 2 <= end for start, end in executable_ranges
        )

    instruction = flash_word(entry)
    require(instruction & 0xFFF == 0x06F, "Entry must be a 32-bit JAL x0 instruction")
    displacement = (
        ((instruction >> 31) & 1) << 20
        | ((instruction >> 12) & 0xFF) << 12
        | ((instruction >> 20) & 1) << 11
        | ((instruction >> 21) & 0x3FF) << 1
    )
    if displacement & (1 << 20):
        displacement -= 1 << 21
    reset_handler = entry + displacement
    require(executable(reset_handler), "Reset jump leaves executable application flash")
    require(flash_word(VECTOR_BASE) == entry, "Invalid reset vector at 0x08007004")
    for index in range(1, VECTOR_COUNT):
        require(
            executable(flash_word(VECTOR_BASE + index * 4)),
            f"Invalid interrupt vector {index}",
        )

    return {
        "status": "layout-valid; hardware-unvalidated",
        "entry": f"0x{entry:08X}",
        "reset_handler": f"0x{reset_handler:08X}",
        "vector_base": f"0x{VECTOR_BASE:08X}",
        "flash_end_exclusive": f"0x{max(end for _, end, _ in flash_segments):08X}",
        "flash_loaded_bytes": sum(end - start for start, end, _ in flash_segments),
        "flash_budget_bytes": FLASH_END - APP_START,
        "ram_static_bytes": sum(end - start for start, end in ram_ranges),
        "stack_reserved_bytes": 2048,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    try:
        report = inspect(args.elf.read_bytes())
    except (OSError, ValueError, struct.error) as error:
        print(f"TS21 image rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
