# Experimental TS21 bring-up

**This is a standalone digital-hardware diagnostic, not an IronOS soldering port.**
It has not been run on a TS21. The pin map is inferred from stock firmware, not
verified against a schematic or measurements. Successful compilation, host tests,
and image inspection do not establish hardware compatibility or safety.

There is no heater-enable path, temperature conversion, PID control, power
negotiation, settings persistence, motion support, or FreeRTOS integration.
The OLED header says `NO HEATING`. TS21 is deliberately absent from the normal
`model=` list and release builds. An explicitly enabled HEX export is available
only for cartridge-removed bench testing. There is no automatic flashing target.
Do not install this as a replacement for stock soldering firmware.

## Build and host tests

Use GNU Make, Python 3, a native C compiler for tests, and a WCH-compatible
RISC-V toolchain with RV32IMAC/ILP32 newlib for the diagnostic. No WCH SDK source
or vendor firmware is needed to build it. The font generator reuses the existing
IronOS ASCII glyphs from `Translations/font_tables.py`.

The tested cross compiler is GCC 8.2.0 from
[Community-PIO-CH32V/toolchain-riscv-linux](https://github.com/Community-PIO-CH32V/toolchain-riscv-linux)
at commit `e8e7ba93c9c1ea30366d98f28318d4ad09b369e2`.
Keep that toolchain on a Linux filesystem: copying a Windows checkout can lose
the Linux library symlinks.

From the repository root in Linux or WSL:

```sh
git clone https://github.com/Community-PIO-CH32V/toolchain-riscv-linux.git "$HOME/ts21-toolchain"
git -C "$HOME/ts21-toolchain" checkout e8e7ba93c9c1ea30366d98f28318d4ad09b369e2
make ts21-bringup TS21_EXPERIMENTAL=1 CROSS_COMPILE="$HOME/ts21-toolchain/bin/riscv-none-embed-"
make test-ts21
```

`make ts21-bringup` refuses to build without the explicit opt-in, even if an ELF
already exists. The board-local equivalent is
`make -C source/Core/BSP/TS21 probe EXPERIMENTAL=1 CROSS_COMPILE=...`.
The host tests do not require the cross compiler or experimental opt-in.

To export an Intel HEX file for a controlled, cartridge-removed diagnostic run:

```sh
make ts21-bringup-hex TS21_EXPERIMENTAL=1 CROSS_COMPILE="$HOME/ts21-toolchain/bin/riscv-none-embed-"
```

The board-local target is `probe-hex EXPERIMENTAL=1`. It creates
`source/Objects/TS21-bringup/TS21_BRINGUP_NOHEAT.hex`, still outside release output
directories. The default `probe` / `ts21-bringup` targets remain ELF-only.
Both diagnostic targets refuse to run without their experimental opt-in.

On Windows, run these tools inside WSL rather than executing the Linux compiler
directly. For example, the host-test command from PowerShell is:

```powershell
wsl.exe -d Ubuntu --cd C:\path\to\IronOS -- make test-ts21
```

Outputs are `source/Objects/TS21-bringup/TS21_BRINGUP_NOHEAT.elf` and its `.map`.
The build runs `tools/inspect_image.py`; its success status is explicitly
`layout-valid; hardware-unvalidated`. It checks ELF headers, load segments,
the entry jump, vectors, flash bounds, and the reserved stack. It does not
validate peripheral behavior or the bootloader's acceptance of an image.

HEX exports are checked record-by-record for syntax, checksums, address bounds,
ordering, entry point, and EOF. Every exported byte/address must match the
validated ELF's loadable flash contents exactly; missing, extra, and changed
bytes are rejected. Only the data, EOF, extended-linear-address, and
start-linear-address record types used by the stock image and `objcopy` are
accepted. A failed export check fails the build, not a warning-only result.

The C tests exercise the real register-access routines with mock MMIO: inhibit
ordering, button and ADC reads, UART receive/error handling, OLED wire bytes,
stuck buses, NACKs, and bounded timeouts. They also check that exercised paths do
not enable the heater timer, raise its control pins, transmit UART data, or
write flash. Protocol coverage includes every pair of payload bytes and recovery
from a corrupt packet. Python tests cover accepted/rejected image layouts and
generation of the existing font, plus valid and malformed HEX exports.
These are software checks, not board tests.

The C files use `source/.clang-format` (checked with clang-format 18); the Python
files use Black and the repository's `.flake8` configuration.

## Cartridge-removed diagnostic flashing

**Remove the cartridge while the iron is unplugged and cool, and leave it out
throughout diagnostic testing.** Software heater inhibition has not been
confirmed electrically. Do not rely on the screen or the build name for safety.

An observed TS21 update device presents a `TS21_DFU` volume and USB ID
`1A86:FE10` (`CH20xUDisk`). Drive letters are not fixed. Verify the model and
update volume rather than copying to an arbitrary removable drive.

Before an experimental flash, keep the official stock v1.5.0 English HEX from
the reference archive below available on the computer. That is a vendor
recovery application, not a dump of the device, its settings, or its bootloader.
Actual restoration from this diagnostic has not been exercised.

The vendor's update procedure, applied only after those prerequisites:

1. Hold the TS21's A button while connecting a USB data cable. Confirm the iron
   shows DFU mode and the TS21 update disk appears.
2. Copy **only `TS21_BRINGUP_NOHEAT.hex`** to that disk's root directory. Do not
   copy the ELF, a whole build directory, or the stock and diagnostic images
   together.
3. Wait for the disk to refresh and the copied file to change from `.hex` to
   `.rdy`, as specified in the vendor instructions. A copy operation completing
   is not itself evidence that the bootloader accepted the firmware.
4. Disconnect and reconnect, keeping the cartridge removed. The expected
   diagnostic display is `NO HEATING` with GPIO button states underneath.
   Display orientation/offset and actual execution still need confirmation.

If the display stays blank, the device resets, or the bootloader reports an
error, stop the diagnostic attempt. Re-enter DFU and use the official stock
`TS21APPV1.5.0EN.hex` by itself to attempt recovery. An error suffix is not proof
that the previous application was left intact. If DFU cannot be entered, USB
file copying is no longer a confirmed recovery route.

## Memory and startup

Ranges below have exclusive upper bounds.

| Region | Range | Use |
| --- | --- | --- |
| Existing bootloader | `0x08000000..0x08007000` | Never part of the diagnostic image |
| Application flash | `0x08007000..0x0800FC00` | 35 KiB maximum |
| Persistent settings reserve | `0x0800FC00..0x08010000` | Never part of the diagnostic image |
| Static RAM | `0x20000000..0x20004800` | Data and BSS |
| Stack reserve | `0x20004800..0x20005000` | 2 KiB |

Stock v1.5.0 EN occupies `0x08007000..0x0800F3B0`, starts with a 32-bit jump,
places the vector table at `0x08007004`, and initializes SP to `0x20005000`.
It accesses persistent settings at `0x0800FF00`; the diagnostic conservatively
reserves the entire last 1 KiB.

`startup.S` initializes GP, SP, data, and BSS, installs the WCH absolute-address
vector table, and enters `main` without enabling interrupts. Unexpected traps
enter the same heater-inhibit loop as fatal initialization failures.
The diagnostic uses 8 MHz HSI and a polling timebase, not the stock 96 MHz PLL.
The watchdog is refreshed if the bootloader has already enabled it.

## Hardware evidence

All stock-code addresses refer to the English v1.5.0 image identified below.
Register layouts were cross-checked against the CH32V20x reference SDK.
Physical signal polarity, board revisions, and bootloader handoff remain
unverified.

| Function | Stock-code evidence | Diagnostic behavior / remaining uncertainty |
| --- | --- | --- |
| MCU | CH32V203-class RISC-V image; stock stack top `0x20005000` | CH32 MMIO and 20 KiB RAM layout; exact hardware revision still needs confirmation |
| OLED bus | PB10 SCL, PB11 SDA; I2C start at `0x0800719E`, byte write at `0x08007248` | Bounded open-drain software I2C |
| OLED protocol | `0x080085A0` sends `0x78`, then control `0x00`/`0x40`; four 128-byte pages | SSD1306-compatible 128x32 initialization; panel offset/orientation not verified |
| Heater timer | TIM3 CH1 on PA6; `0x08008E70` sets PSC 0, ARR 959, CCR1 96 at stock 96 MHz | Timer/channel disabled, compare zero, PA6 driven low |
| Apparent heater gate | PA10 is cleared at startup and before ADC work at `0x080075E6` | PA10 driven low before timer reconfiguration; active-high enable is an inference, not a measured fact |
| Buttons | `0x08007CB0` configures PA5 and PA7 with pull-ups | Active-low GPIO labels only; physical A/B assignment unverified |
| Analog inputs | `0x080074C0` configures PA1, PA2, PA4, PB1; ADC channels 1, 2, 4, 9 | Raw 12-bit readings only; no temperature or voltage calibration |
| Analog switching | Sampling at `0x080075E6` sets PB15 and toggles PA0 around channel-1 reads | Not reproduced; front-end switching, gain, and cold-junction sensing are unresolved |
| Power telemetry | `0x08009322` configures USART2 RX on PA3 at 9600 baud; handler at `0x080093B4` | RX only; PA2 remains analog; no TX, voltage request, or power-contract assertion |

The diagnostic's OLED initialization uses an ordinary 128x32 configuration.
Stock orientation code at `0x080085DA` uses `D3 30 C0 A0` in one orientation;
that panel-specific offset must be checked on hardware before assuming the
diagnostic screen will be visible or correctly oriented.

USART2 frames are four bytes: `FF, voltage_byte, status_byte, CRC`.
The CRC is Dallas/Maxim CRC-8 (reflected polynomial `0x8C`, initial zero) over
the first three bytes. Stock code multiplies the voltage byte by 1000 for
millivolts. The status byte and the controller producing these frames are not
identified. A valid frame is not proof of an available or safe power contract.

Stock code also depends on private bootloader services: the dispatcher at
`0x0800B368` calls `0x08006A30` with operations 0 through 4. Operation 3 returns
six bytes used as motion XYZ samples. Other callbacks are loaded from
initialized RAM. Stock identity checking uses data near `0x08006FF0`.
The diagnostic neither calls these services nor modifies their storage.

## Diagnostic output

The permanent first line is `NO HEATING`. PA5 advances the page and PA7 goes
back after debouncing; these are GPIO names, not established physical A/B labels.

| Page | Second line |
| --- | --- |
| 0 | `5:0 7:0` pressed-state bits |
| 1..4 | `1:NNNN`, `2:NNNN`, `4:NNNN`, `9:NNNN` raw ADC values, or `ADC ERROR` |
| 5 | `U:NNNN` last voltage byte, or `UART WAIT` before a valid frame |
| 6 | `X:NNNN` last status byte, or `UART WAIT` before a valid frame |
| 7 | `E:NNNN` latched error bitmask in decimal |

The UART pages show the **last received bytes**, not a live voltage measurement.
The volatile `ts21_status` structure is also available to a debugger: signature
`0x54533231`, iteration count, ADC validity mask, button/page state, error flags,
valid frame count, and the last frame timestamp in microseconds.
The timestamp is a wrapping 32-bit counter.

| Bit | Error |
| --- | --- |
| `0x01` | Clock readiness, switching, or timebase timeout |
| `0x02` | ADC calibration or conversion failure |
| `0x04` | I2C bus fault |
| `0x08` | I2C NACK |
| `0x10` | UART receive error |
| `0x20` | Invalid API argument |
| `0x40` | Unexpected trap or return from main |

ADC failures invalidate the reading rather than substituting a successful zero.
Fatal clock/display/trap paths repeatedly inhibit the heater and refresh the
watchdog. A display failure can leave the screen blank or stale; inspect the
status structure rather than interpreting the screen as evidence of safety.

## Requirements before a usable port

1. Confirm the PCB revision, heater-gate polarity, timer pin, and reset/fault
   behavior by measurement with the cartridge disconnected and a recovery path
   available. Software-only pin assumptions are not sufficient to permit heating.
2. Establish the thermocouple switching sequence, gain, ADC scaling, cold-junction
   compensation, and disconnected-tip detection. Do not reuse S60 calibration
   just because both irons use C210 cartridges.
3. Identify the power controller and validate telemetry, voltage/current limits,
   and bootloader-owned services, including motion and cartridge-related storage.
4. Verify OLED initialization, button mapping, clock timing, and bootloader
   handoff on hardware; then integrate a suitable WCH FreeRTOS port and the
   normal IronOS BSP interfaces within the flash/RAM budget.
5. Only after the input measurements and independent heater inhibition are
   established, validate temperature control and fault shutdown under controlled
   hardware testing. Do not add TS21 to supported models before that work.

## Reference provenance

- [Upstream TS21 support request](https://github.com/Ralim/IronOS/issues/2122).
- [Official Miniware TS21 v1.5.0 archive](https://forum.minidso.com/forumdownload/TS21APPV1.5.0.zip):
  SHA-256 `24c74454ac876b8fb2d43b2b5cfe4de3fdcb3109d6f2b6349fc5d676a9a6082b`.
- `TS21APPV1.5.0EN.hex`:
  SHA-256 `786ae2d3bb5702b50ce2d628891b3bf07a4580bfc9a2ea974db69e46ab8882c8`.
- [WCH CH32V20x SDK](https://github.com/openwch/ch32v20x/tree/baef0054588f4826548429ff4e7a9257d752ef2f),
  including the D6 startup and FreeRTOS references.
- The toolchain revision above includes patched binutils 2.32. For stock-image
  disassembly use its `objdump` with `-M numeric,xw`: generic RISC-V disassemblers
  misinterpret WCH compressed byte/halfword instructions as floating-point
  operations.

Stock firmware and toolchain binaries are analysis/build references only and
are not redistributed in this directory. Existing project and dependency
license notices remain applicable.
