.DEFAULT_GOAL := help

ROOT := $(abspath ../../../..)
OUT ?= $(ROOT)/source/Objects/TS21-bringup
CROSS_COMPILE ?= riscv-none-embed-
HOST_CC ?= cc
PYTHON ?= python3

ARCH_FLAGS := -march=rv32imac -mabi=ilp32
WARNINGS := -Wall -Wextra -Werror
CFLAGS := $(ARCH_FLAGS) $(WARNINGS) -std=c11 -Os -g3 -ffreestanding \
          -fno-builtin -fno-common -ffunction-sections -fdata-sections -fno-jump-tables \
          -I. -I$(OUT)
OBJECTS := $(OUT)/startup.o $(OUT)/main.o $(OUT)/hardware.o $(OUT)/protocol.o
ELF := $(OUT)/TS21_BRINGUP_NOHEAT.elf

.PHONY: help probe test
help:
	@echo "Development-only TS21 no-heater diagnostic, NOT an IronOS soldering port."
	@echo "make probe EXPERIMENTAL=1 CROSS_COMPILE=<toolchain-prefix>"
	@echo "make test"
	@echo "Only an ELF is produced; no HEX/DFU images or flashing targets."

ifeq ($(EXPERIMENTAL),1)
probe: $(ELF)
	$(PYTHON) tools/inspect_image.py $(ELF)
	@echo "UNVALIDATED HARDWARE: ELF is for bring-up, not normal soldering."
else
probe:
	@echo "Refusing experimental build without EXPERIMENTAL=1. Read README.md."
	@exit 1
endif

$(OUT):
	mkdir -p $@

$(OUT)/font.h: tools/generate_font.py $(ROOT)/Translations/font_tables.py | $(OUT)
	$(PYTHON) $< $@

$(OBJECTS): Makefile

$(OUT)/main.o: main.c ts21.h $(OUT)/font.h
	$(CROSS_COMPILE)gcc $(CFLAGS) -c $< -o $@

$(OUT)/%.o: %.c ts21.h | $(OUT)
	$(CROSS_COMPILE)gcc $(CFLAGS) -c $< -o $@

$(OUT)/startup.o: startup.S | $(OUT)
	$(CROSS_COMPILE)gcc $(ARCH_FLAGS) -c $< -o $@

$(ELF): $(OBJECTS) ts21.ld Makefile
	$(CROSS_COMPILE)gcc $(ARCH_FLAGS) -nostartfiles -nostdlib \
		-Wl,--gc-sections,--build-id=none,-Map,$(OUT)/TS21_BRINGUP_NOHEAT.map \
		-T ts21.ld $(OBJECTS) -lc -lgcc -o $@
	$(CROSS_COMPILE)size $@

$(OUT)/host-tests: tests/host_tests.c hardware.c protocol.c ts21.h Makefile | $(OUT)
	$(HOST_CC) $(WARNINGS) -std=c11 -DTS21_HOST_TEST -I. tests/host_tests.c hardware.c protocol.c -o $@

test: $(OUT)/host-tests
	$(OUT)/host-tests
	$(PYTHON) -m unittest discover -s tests -p '*_test.py'
