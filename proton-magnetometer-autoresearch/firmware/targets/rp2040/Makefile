# C4: cross-compile the estimator core for the RP2040 emulator check.
# Needs arm-none-eabi-gcc (e.g. the ARM GNU Toolchain tarball); set
# ARM_GCC to its bin dir (with trailing slash), e.g.
#   make -C firmware/targets/rp2040 ARM_GCC=~/tools/arm-gnu-toolchain-.../bin/
# Builds an SRAM image loaded by sim/rp2040js/run_fid_est.js (no boot2:
# the emulator starts the core from the vector table's SP/PC).

HERE  := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ROOT  := $(HERE)../../../
CC    := $(ARM_GCC)arm-none-eabi-gcc
BUILD := $(HERE)build/

all: $(BUILD)fid_est.bin

$(BUILD)fid_est.elf: main.c $(ROOT)firmware/core/freq_est.c \
		$(ROOT)firmware/core/freq_est.h $(ROOT)firmware/targets/fid_vector.h
	mkdir -p $(BUILD)
	$(CC) -std=c99 -O2 -mcpu=cortex-m0plus -mthumb -ffreestanding \
		-ffunction-sections -fdata-sections \
		-I$(ROOT)firmware/core -I$(ROOT)firmware/targets \
		-nostdlib -Wl,-T,$(HERE)rp2040_sram.ld -Wl,--gc-sections --specs=nano.specs \
		-Wl,-Map=$(BUILD)fw.map -o $@ main.c \
		$(ROOT)firmware/core/freq_est.c -lc -lm -lgcc -lnosys

$(BUILD)fid_est.bin: $(BUILD)fid_est.elf
	$(ARM_GCC)arm-none-eabi-objcopy -O binary $< $@

test: $(BUILD)fid_est.bin
	node $(ROOT)sim/rp2040js/run_fid_est.js $(BUILD)fid_est.bin

.PHONY: all test
