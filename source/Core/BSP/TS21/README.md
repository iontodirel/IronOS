# Experimental TS21 IronOS port

## C210 temperature-controlled test build

`ts21-ironos` still hard-disables heating. The separate opt-in below builds the
normal IronOS UI with a real, restricted heater path:

```sh
make ts21-heater-test TS21_EXPERIMENTAL=1 CROSS_COMPILE="$HOME/ts21-toolchain/bin/riscv-none-embed-"
make test-ts21
```

The image is
`source/Hexfile/TS21-heater-test/TS21_font_compressed_EN.hex`, not
`source/Hexfile/TS21_EN.hex`. Both root build targets force regeneration to
avoid reusing another model/variant's generated settings or translations.
Both TS21 IronOS variants use the existing lossless font and string compression
formats to stay inside the unchanged 35 KiB application region. The two font
buffers and translation data are decompressed before use; their pixels, text
and the full 128x32 UI are unchanged. Bootloader/settings boundaries and the
2 KiB boot/IRQ stack reserve are not reduced.

### Front work light

**Settings -> User interface -> Work light** switches the front LED on or off.
It defaults off, persists across power cycles and remains independent of
heating. The GUI applies the setting after rendering, including after a
factory reset. Existing settings are preserved when the new setting is appended;
the standard settings-update notice may appear on the first boot. Untranslated
optional menu text uses the declared English fallback.

Stock v1.5.0 configures PA9 as a push-pull output: the initialization at
`0x0800BE98` uses GPIOA mask `0x0601` and GPIO mode `0x10` at speed `3`.
Its light-setting byte at offset 21 selects PA9 mask `0x0200` high or low at
`0x08007EAC..0x08007ED8`; the set/reset helpers at `0x0800CA92` and `0x0800CAA6`
write GPIO BSHR/BCR. This port retains that active-high polarity. It clears
the latch before enabling the output and subsequently writes only PA9.
PA6/PA10 heater controls, sensor pins and timers are untouched.

Native checks exercise both LED states, including while the heater gate is
active, and verify migration of all 57 previous settings plus on/off persistence
using the real settings code. The actual-ELF `--check-worklight off` and `on`
cases check boot state without heating. `--check-worklight menu` selects the
real User interface descriptor, uses GPIO button presses to toggle it, checks
the checkbox pixels and PA9 state, then verifies the saved flash record on exit.
Use `--instructions 200000000` for the menu case.

**This is a supervised bring-up image, not normal soldering firmware.** Use a
current-limited source, a nonflammable holder and an independent temperature
probe. Verify reset/fault-off and the PA10 gate expiry with the cartridge
disconnected before a powered cartridge test. Do not touch the tip to check
whether this image heats. The software wattage and temperature limits depend
on stock-derived ADC conversions; they are not calibrated measurements, a
hardware current regulator, or protection against a failed-short power device.
No active USB-PD request is sent, and passive UART telemetry is not treated as
proof of a power contract.

The first heater image incorrectly treated every recorded error, including a
passive UART receive overrun, as a disconnected tip. A receive overrun with
valid sensor values reproduces that false indication and prevents entering
soldering mode. UART reception errors now remain recorded for diagnosis but
do not veto tip connection or heating: neither the power calculation nor
heater permission depends on those receive-only packets. Every other error
bit remains inhibiting, including unknown bits, and all sensor/resistance
limits are unchanged. This identifies a reproducible firmware bug, not proof
that UART caused the reported physical device's indication.

If the indication persists, inspect the existing debug menu without heating:
hold the top button from home, use the bottom button to cycle through input
voltage, tip/handle temperature and tip resistance, and use a short top press
to exit. Do not lower resistance limits or bypass invalid samples to force
the soldering screen open.

On each boot it starts unarmed at the normal home screen. Saved autostart,
boost and power-bank keepalive are overridden in RAM. The saved soldering
temperature is preserved rather than forced back to the earlier 90 C test
setpoint. The usual **10..450 C / 50..850 F** controls are available; the
factory default is **320 C**. The experimental 100 C ceiling is removed,
not the normal setpoint limits or fault protections.
The power-limit setting is initialized to 100 W in RAM,
including when the previous build saved a 5 W limit; it can still be reduced
in settings but cannot raise the driver's ceiling.
A bottom-button press/release from home is required
to arm heating; the top button still opens settings. Heating is only permitted
in the ordinary soldering mode, with a positive target and fresh GUI activity.
The screen stays awake during this bench test.

The estimated output is capped at **100 W**, independently of the user's voltage
calibration or requested PWM. The controller is the same shared IronOS
decaying-integrator path used by SEQURE S60/S60P, with their C210 parameters:
thermal mass 10 and inertia 128. S99 is a C245 model with different tuning.
The TS21 keeps its own stock-derived ADC/NTC/resistance conversions, carrier
frequency and shutdown gate; SEQURE analog calibration and timer registers
are not portable to this board. Starting/resuming the shared controller after
idle, or calling it twice in one tick, uses the nominal rate rather than
dividing by zero.

[Miniware specifies adjustable power up to 100 W for the TS21](https://e-design.com.cn/ProductDetail/10747118.html),
with PD input and 210-series tips. That is the device rating used for this
ceiling, not a command to continuously apply 100 W. The separate
[JBC T210 handle's 40 W peak rating](https://www.jbctools.com/product_datasheet.php?id=48)
is not the TS21's rating; neither specification establishes that every
replacement cartridge or power source is suitable for the same conditions.

For a 100 W-capable setup within this port's voltage range, use a suitable
20 V / 5 A PD source and a 5 A e-marked cable, with a suitable TS21 cartridge.
The port does not issue active PD requests or establish the negotiated current
budget from its passive telemetry. A 100 W setting does not itself obtain a
100 W contract. Use a lower user power limit before heating if the qualified
source/cartridge limit is lower. Actual output is also bounded by voltage,
resistance and the retained 85% carrier duty ceiling.

Requests consume a valid sensor sample no older than
20 ms. Each accepted request produces at most a 120 ms gate pulse, with a
150 ms software command deadline. Both tasks and interrupt execution may stop
without extending that hardware pulse. A missing GUI update for 500 ms also
removes permission to heat.

This image accepts measured resistance from 1.0 through 10.0 ohms and input
voltage from 4.5 through 21.0 V; these are conservative test acceptance bounds,
not claimed cartridge specifications. Short/open resistance, invalid sensors,
invalid supply, handle temperature outside 0..60 C and tip temperature at or
above **500 C** inhibit output. This is a separate sensor-range/overtemperature
fault threshold above the normal operating setpoints. Faults latch until reboot.
There is **no fixed three- or five-second heating-session cutoff**. Normal
temperature control continues until the user exits or a protection acts.
The board requires at least 3 C progress within a 20-second window while the
tip is at least 3 C below target **and heating is at its effective power ceiling**.
The ceiling uses the shared controller's available-power, user, supply, hardware
and optional derating limits, converted to PWM and clamped by the driver's raw
power and duty limits. Only an accepted full-effort command starts this window;
progress restarts it, while partial/zero power, being near target or idle resets it.
Full effort after warm-up starts a fresh window, so an earlier successful rise
does not excuse a later stalled full-power heat-up.
The shared C210 decaying integrator can legitimately hold a steady temperature
slightly below target at partial power. The previous guard incorrectly demanded
another 3 C rise every 20 seconds even in that state, reproducing `00002000` at a
stable 315 C with a 320 C target. Normal partial-power holding no longer trips
this extra guard; genuine no-response heating and the other protections remain.
The rise check uses the same effective Celsius target as the shared controller:
the 850 F selection converts to 454 C, but the controller limits it to 450 C.
That normal conversion must not produce a false no-rise fault at 450 C.
An inadequate supply can still make setpoints slow or unreachable; do not
bypass a protection trip to compensate for insufficient power.

These are sensor-based controls, not unconditional physical temperature
guarantees. Calibration error, thermal overshoot or a failed power device
requires independent measurement and protection. Previous 100 C and timed-test
artifacts remain separate and unchanged.
The normal warning screen now says **Heating stopped** and shows an eight-digit
hexadecimal stop code. It stays visible until a button acknowledges it, even
if the last button press was more than five seconds ago. Acknowledging it does
not clear the fault: the home screen reports the current tip connection, and
another bottom-button start only reopens the stop warning without arming or
heating. Passive UART diagnostic bits are excluded from this displayed code.
The rise watchdog stops with the fault, so cooling afterward does not add
another no-rise fault.

| Stop code | Meaning |
| --- | --- |
| `00002000` | Less than 3 C progress within 20 seconds of full-effort heating below target |
| `00000400` | Missing, consumed or stale sensor/control update |
| `00000200` | Resistance below the short-circuit threshold |
| `00008000` | Open/clipped or out-of-range high resistance reading |
| `00004000` | Input voltage outside the accepted test range |
| `00001000` | Tip/handle temperature outside the accepted range |
| `00000100` | Invalid sensor conversion |
| `00010000` | The shared IronOS thermal monitor stopped heating |

Codes are a bitmask; multiple flags can be combined. Other bits are defined in
`ts21.h`. A shared thermal-monitor stop is also latched by the board driver
before it is displayed, so acknowledging it cannot permit a restart.
`00000800` belongs to the previous timed test; this build does not generate it.
Unplug after recording the code and readings.

The earlier heater images used **Thermal Runaway** for every latched stop,
then automatically dismissed it using the time since the last button press.
They also presented any latched heater fault as **tip disconnected**.
Thus a no-rise/test-timeout stop could produce both reported messages without
an unplugged cartridge or an observed overtemperature. Those messages alone
cannot identify what actually stopped the physical device.

### Heater evidence and implementation

Stock v1.5.0 sets PA10 immediately before heating at `0x0800BA7E`, and clears it
at `0x080075EE` before the two-phase ADC sample and at `0x0800BB62` when stopping.
Its `0x08008E70` setup uses PA6 / TIM3 channel 1, active-high PWM1, prescaler 0,
period 959 at 96 MHz: a 100 kHz carrier. This port uses period 639 at its
64 MHz timer clock. TIM3 outputs are off during all five ADC measurements.

The stock routine at `0x0800BBF4` subtracts the low-phase ADC1 reading from
the high-phase reading, divides by 177 and multiplies by 1000 to obtain
milliohms. The divisor's float value is stored at stock flash `0x0800F374`.
The port computes tenths of an ohm with integer arithmetic, rounding down.
It bounds PWM using `P = V^2 / R`, rounding voltage up; changing the saved
voltage calibration cannot increase this raw-ADC-based ceiling. No resistance
is inferred from cartridge marketing or copied from another board.
ADC4's stock threshold of 1999 is associated with stand state, not verified
heater-current measurement, and is not repurposed as a current sensor.

PA10 is additionally assigned to the documented TIM1 channel 3 alternate
function. This independent timer uses a 1 kHz count, PWM2 with compare 1,
period 120 and one-pulse mode. The gate is low initially, high for counts
1..120, and low again when the timer stops at the update. This is a new
fail-safe addition, not a claim that the stock firmware already implements it.
Only TIM3 CH1 and TIM1 CH3 are enabled; inherited remapping/timer state is reset
while the gate is low. Sampling, settings writes, reboot and trap paths inhibit
output. Settings inhibition occurs after masking interrupts, so a task switch
cannot rearm it between shutdown and flash programming.

The MCU's independent watchdog is configured to a nominal 500 ms at 40 kHz
LSI. The finite PA10 pulse, not idle-task watchdog refresh, bounds a stalled
controller's output. The native tests cover all duty/mode combinations, raw
power ceilings, sample consumption/age, GPIO/timer sequencing, invalid sensors,
open/short resistance, supply/temperature bounds, command expiry, recurring
no-rise protection and continued near-target operation across microsecond
rollover. They also cover a minute-long partial-power hold below target, renewed
full-effort demand, reduced user/supply ceilings and zero-power window reset.
Normal-temperature operation and the 499/500 C fault boundary are
checked explicitly. Power history uses the accepted
timer duty's raw-ADC-based power estimate, rather than a second lossy conversion
through eight-bit PWM or reporting rejected requests as delivered power.
The stored tenths-watt readback is 16-bit, so values above 25.5 W do not wrap.
Tests explicitly cover both the low-voltage duty-limited output and the
approximately 99.7 W quantized estimate on the 20 V / 2 ohm fixture.

The optional actual-ELF emulator also exercises the real GUI and PID task:

```sh
python3 source/Core/BSP/TS21/tools/emulate_boot.py \
  source/Hexfile/TS21-heater-test/TS21_font_compressed_EN.elf \
  --prefix "$HOME/ts21-toolchain/bin/riscv-none-embed-" \
  --inherited-interrupt --max-frame-us 60000 \
  --check-heater short --instructions 160000000
```

Run with `startup`, `short`, `open`, `supply`, `overtemp`, `stall`, `continuous`, `range`,
`hold`, `no-rise`, `uart` and `monitor`, and
exercise both interrupt-inherited and reset-context entry. It seeds saved
autostart/boost/keepalive, a saved normal-range setpoint and the previous 5 W power
setting, verifies unarmed startup, presses/releases the real
bottom GPIO input, and requires bounded nonzero output before fault injection.
The cold 20 V fixture must reach the new 100 W ceiling within timer resolution,
with untruncated power accounting, rather than merely producing some output.
It also ages the cold soldering screen's inactivity timestamps and rejects
display blanking in this bench variant.
Fault runs require output inhibition, a fully rendered stop code that stays
until acknowledged, correct tip-connection reporting afterward and rejection
of a bottom-button restart;
the stall run advances only the timer model after CPU execution is stopped.
The `uart` run injects a receive overrun before the home-screen button action,
requires the diagnostic error to stay recorded while a valid tip can heat
within the existing bounds, and then requires a short-circuit fault to stop
output normally. Native checks cover all four UART receive-error flags and
ensure every other error bit still inhibits output, including when combined
with a UART error.
The `no-rise` run ages only the rise-watchdog timestamp for a fault check.
The `range` run verifies that a saved 320 C or 850 F selection is retained,
can heat above the old 100 C ceiling within the power limit, and does not trigger the
rise watchdog at its effective target. It then checks the 500 C fault cutoff.
Use `--check-heater range --instructions 200000000`, with `--fahrenheit` for
the upper Fahrenheit setting.
The `hold` run injects a steady temperature 5 C below the effective target,
requires real controller modulation with the rise window cleared, and ages
only the rise timestamp across multiple holding commands. It then returns to
a cold fixture, requires a fresh full-effort window, and verifies a genuine
20-second no-rise stop with the normal warning and restart lockout.
Use `--check-heater hold --instructions 200000000`; `--fahrenheit` also exercises
holding below the effective 450 C target.
The `continuous` run uses a scripted temperature rise, verifies controller
modulation and continued operation beyond six seconds, then injects the exact
500 C reading and checks shutdown and restart lockout. Use
`--check-heater continuous --instructions 600000000` for its longer budget;
`--fahrenheit` also exercises saved Fahrenheit settings. Native tests exercise
continued operation for over a minute, renewed rise demand, counter rollover,
and the actual shared controller's cold-start, idle and same-tick arithmetic.
These are not hardware timing, energy or thermal measurements.
Compressed fonts and translation buffers are compared byte-for-byte against
host decompression. Heater runs also keep the light enabled and verify that
sampling, PWM and fault shutdown do not change its selected state.
This remains instruction/peripheral simulation, not electrical or thermal
validation of a TS21.

## Normal IronOS, heater disabled

`make ts21-ironos TS21_EXPERIMENTAL=1 CROSS_COMPILE=<prefix>` builds the real
IronOS application: the existing GUI, menus, buttons, settings, PID task and
FreeRTOS kernel. Its image is `source/Hexfile/TS21_EN.hex`; this is **not** the
standalone diagnostic described later in this document. Nothing custom is
added to the screen.

This remains a development port, not supported soldering firmware. The earlier
diagnostic was accepted by the TS21 bootloader (`.rdy`) and booted on one device.
Its `A1/C8` display orientation was upside down. The IronOS target uses the
stock panel mapping: `A0/C0/D3 30` normally, `A1/C8/D3 10` when rotated, and
sequential COM wiring. The full normal UI is now confirmed on the device.
The user has also confirmed that the revised UI looks good and the temperature
reading responds to gentle external warming. Sensor accuracy and electrical
heater inhibition still require independent confirmation.

The first full IronOS image was subsequently accepted as `I21OS.rdy`: 99,985
Intel HEX bytes containing 35,524 application bytes, within the 35,840-byte
budget. Its HEX SHA-256 is
`753512288934168dfe446d803b13c574b5ec4eb37e8a80a485b14fd0a34f4eda`.
This records updater acceptance, **not** observed execution of the full port.

That first image subsequently failed on hardware with only a flashing logo.
Its RTOS startup called `main` directly instead of using the `mepc`/`mret`
handoff used by both the stock TS21 image and WCH's FreeRTOS startup. An
inherited bootloader interrupt context can then suppress the low-priority
software/timer interrupts, leaving the first task unable to yield to the GUI.
Startup now configures the WCH instruction pipeline and enters `main` through
`mret`, with an unexpected return directed to the inhibited fault handler.
Instruction-level simulation reproduces the missing-GUI failure for the old
entry with an active interrupt and reaches the normal GUI with the corrected
entry, both with and without that inherited state. This is a simulated handoff
regression, not a measured hardware trace.
The corrected image was accepted as `I21FIX.rdy` (35,548 application bytes);
its HEX SHA-256 is
`53a578226cc11163faf98cb346891285e43aba96b758d985fbe07d70d9bf61d7`.
The user subsequently confirmed that this image reaches the UI, but half of
the screen was clipped. The zero display offset was incorrect for the panel.
TS21 now enables the existing `OLED_DISPLAY_OFFSET_QUIRK` path: the stock
orientation routines at `0x080085DA` and `0x08008DC4` specify offsets `0x30`
and `0x10` alongside their matching COM/segment directions. The interface
remains 128x32; no rows, columns or controls are removed to hide the clipping.

The display-mapping image was accepted as `I21LCD.rdy` (100,120 Intel HEX
bytes; 35,572 application bytes). Its HEX SHA-256 is
`9eb9947c76f8868125e9b669152975f52ef2fbb74b6de22346f40a9b2b86f31e`.
The user confirmed that the complete UI works, then reported sluggish response
and reversed top/bottom button actions.

The normal IronOS target now maps PA5 (top) to logical B: a short press/release
opens settings. PA7 (bottom) maps to logical A and the normal soldering screen,
still with no heater output. Long-press and simultaneous-button behavior remain
the shared IronOS implementation; the bootloader's DFU button is unchanged.

The application no longer uses the diagnostic's 8 MHz core clock. It selects
the WCH HSI-fed PLL at 64 MHz (undivided 8 MHz HSI x8), with APB1 at 32 MHz,
APB2 at 64 MHz and ADC at 8 MHz. The 8 MHz free-running counter is converted
back to microseconds; RTOS ticks stay at 1 kHz, receive-only UART stays at 9600
baud, and sensor settling delays retain their original durations. The power-of-two
counter clock avoids pulling a large 64-bit division routine into the 35 KiB
application region. A 96 MHz version exceeded that protected budget.

OLED data/ACK clocks use 2 us minimum half-periods, at most 250 kHz before
software overhead; start/stop delays remain 4 us. Stock TS21 byte output at
`0x08007248` uses the short delay loop at `0x08007186`, rather than requiring
slow transfers. The working command framing, page transfers and panel offsets
are unchanged. Clock-lock/switch failures and I2C errors remain bounded and
fatal with heating inhibited. The standalone diagnostic retains its 8 MHz clock,
4 us data/ACK delays and raw GPIO button labels.

The optional startup regression uses the actual linked ELF with simulated
peripherals; it does not replace on-device observation. In a development Python
environment, install `tools/requirements-emulation.txt` from this directory,
then run from the repository root:

```sh
python3 source/Core/BSP/TS21/tools/emulate_boot.py source/Hexfile/TS21_EN.elf \
  --prefix "$HOME/ts21-toolchain/bin/riscv-none-embed-" --inherited-interrupt \
  --max-frame-us 60000
```

Repeat without `--inherited-interrupt` for a reset-context entry. Both must reach
the normal GUI, transfer at least two framebuffers and service timer interrupts
without driving the heater pins high. This dependency is not required for normal
firmware builds or the existing native tests.

In this instruction-count model, the old 8 MHz image took 106-146 ms per
frame transfer; the 64 MHz/faster-bus image takes 37-39 ms and passes the same
60 ms limit in both entry contexts. These are simulated transfers, not measured
panel refresh rates or guaranteed button latency. The new image contains 35,732
application bytes, with HEX SHA-256
`df699ef30a5801bcb8ca4e6932343def7715835f18ebd73441b81947f1d59b95`.
This image was accepted as `I21FAST.rdy` (100,570 Intel HEX bytes), after which
the user confirmed the improved UI and a low-temperature response. This is not
a measured clock check or temperature calibration.

Cold-tip bench testing then exposed the normal screen-blanking policy: below
50 C, a nonzero motion-sensitivity setting enables blanking after one minute
without movement or button activity. This port has no movement detection to
wake the screen. Heater-disabled builds now keep the GUI display on so external
temperature tests remain visible. Ordinary heating-enabled builds retain their
existing blanking policy; no settings are reset and the heater lockout is unchanged.
Unplug the bench device when finished to avoid unnecessarily leaving the OLED on.

Add `--check-cold-display` to the emulator command to exercise this case. It seeds
saved motion sensitivity and autostart settings, enters the real soldering UI,
and ages the two activity timestamps by 61 seconds without skipping scheduler
ticks. It requires the display to stay on for three subsequent redraws and
rejects an OLED-off command. The preceding image reproduces the reported blanking;
the corrected image stays on. This is a controlled inactivity-state simulation,
not a minute-long hardware endurance test.

An earlier screen-awake-only candidate contained 35,640 application bytes; its HEX SHA-256 is
`bcd1b9841b880f62d3ff1b54553e168d60da0a7faab66c4201f888ae7224abd3`.
That candidate was not flashed. The first-heating variant also includes this
display correction; its on-device behavior still needs confirmation.

In the default `ts21-ironos` build, the heater lockout is unconditional in
`setTipPWM()`: every requested duty cycle
and both PWM modes disable TIM3 and hold PA6/PA10 low. `HEATER_DISABLED` also
forces IronOS's requested and reported output power to zero. Settings, autostart,
boost and power-bank keepalive cannot enable it. Only the separate
`ts21-heater-test` target above includes a heater-enable path.

Build with the WCH toolchain below, Python dependencies from
`Translations/requirements.txt`, GNU Make and native C/C++ compilers:

```sh
make ts21-ironos TS21_EXPERIMENTAL=1 CROSS_COMPILE="$HOME/ts21-toolchain/bin/riscv-none-embed-"
make test-ts21
```

Native tests exercise all 512 BSP PWM level/mode requests, zero requested and
reported IronOS heater power, inherited interrupt reset, sensor conversion and
failure paths, and all 56 columns of each four-row mirrored home-screen asset.
They also execute the actual OLED driver to check its startup and both rotation
command sequences and every byte of all four 128-column framebuffer pages.
Both diagnostic and IronOS clock configurations are covered, including PLL
failures, UART divisor, counter rollover, microsecond delays and OLED edge timing.
The shared button decoder and home-screen actions are exercised for menu entry,
the soldering-screen action, 400 ms holds and simultaneous-button release.
The image-tool tests check the protected memory ranges and exact HEX contents.

The equivalent source target is
`make -B -C source model=TS21 TS21_EXPERIMENTAL=1 TS21_HEATER_TEST=0 COMPILER_PREFIX=<prefix-without-final-dash> Hexfile/TS21_EN.hex`.
`HOST_PYTHON` can select a virtual environment. TS21 is not included in release
matrices. Without the experimental opt-in even an existing image is refused.
The same strict ELF/HEX byte comparison and protected memory bounds apply.

The `IronOS/` BSP uses the existing application entry point, not `main.c` in this
directory, and excludes host tests from embedded source discovery. Its small
CMSIS API adapter calls the existing FreeRTOS kernel directly; ST-only CMSIS
implementation sources are not used on this MCU. The MIT-licensed WCH RISC-V
port is in `IronOS/Port`, with its notices retained. Adaptations are self-contained
header includes, four-byte handler alignment, compiler barriers around interrupt
masking/stack switching, and a 1 kHz tick reload from the free-running 8 MHz
counter so the I2C/ADC delays keep working after the scheduler starts.
Reload accounts for delayed interrupts
and low-word rollover. Interrupts
left enabled by the bootloader are disabled/cleared before scheduler startup.

Sensor sampling follows the stock PA10-low, PB15-high, PA0-high/low sequence
with 200/600/800 microsecond settling delays. It reads both phases of ADC1,
ADC2 (handle thermistor), ADC9 (input voltage), then ADC4 after releasing PB15.
The D6 ADC calibration uses both internal reference levels. Stock v1.5.0's
numeric conversion evidence is implemented independently:

- Tip delta: `x = ADC1_low - 563`; degrees C = `-0.00001*x*x + 0.2006*x - 3.1236`.
- Handle: interpolation of the ADC2 thermistor curve, -30 to 125 C, added as
  cold-junction compensation. The sparse 5 C table still needs comparison with
  an external reference thermometer.
- Input: volts = `ADC9*0.0069 - 0.0088`, with IronOS's voltage adjustment.

These are inferred factory transfer functions, **not measured calibration of
this board or cartridge**. Invalid ADC/thermistor readings latch sensor errors
and mark the tip unavailable. The unknown thermocouple gain is not replaced
with S60 values: the microvolt debug fields show the normal unavailable icon,
and microvolt-based CJC calibration is not offered.

Settings occupy only the 256-byte page at `0x0800FC00`. Saving uses the WCH
256-byte fast erase, never the 4 KiB normal erase. Bootloader code and Miniware's
settings at `0x0800FF00` are not erased. Writes are bounded, read back and checked;
failures inhibit the heater and latch a flash error. Like other single-page
IronOS settings implementations, this is not power-loss-atomic.

Motion/private bootloader services, active PD negotiation and custom boot logos
are not implemented. Heater drive and resistance fault checks are restricted
to the first-heating variant described above; there is no full-power TS21 port.
Power telemetry remains receive-only; no high-voltage request is sent.
Automatic rotation and motion sleep are disabled. Do not infer heating readiness
from a booting GUI or a plausible temperature number.

For this image use the DFU procedure below but copy **`TS21_EN.hex`**, then wait
for `.rdy`. Reconnect normally to see the standard IronOS interface. Keep the
cartridge removed for first boot, as for the previously confirmed diagnostic.

## Earlier standalone diagnostic

**This is a standalone digital-hardware diagnostic, not an IronOS soldering port.**
It has booted on one TS21, with an inverted but readable display. The pin map is inferred from stock firmware, not
verified against a schematic or measurements. Successful compilation, host tests,
and image inspection do not establish hardware compatibility or safety.

There is no heater-enable path, temperature conversion, PID control, power
negotiation, settings persistence, motion support, or FreeRTOS integration.
The OLED header says `NO HEATING`. It is separate from the experimental
`model=TS21` IronOS target and release builds. An explicitly enabled HEX export is available
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
   This diagnostic's orientation is inverted on the observed device.

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
| `0x80` | IronOS settings flash operation or readback failure |
| `0x100` | IronOS sensor reading unavailable or outside its conversion range |

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
