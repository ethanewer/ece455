PYTHON ?= python3
# Bench tools (plotter, flasher) run from a local virtual environment that
# `make plot` and `make flash` create on first use.
VENV ?= .venv
BENCH_PYTHON := $(VENV)/bin/python
BENCH_STAMP := $(VENV)/.bench-installed
# Pico build: SDK and Arm toolchain where the Pico VS Code extension puts them.
PICO_SDK_PATH ?= $(HOME)/.pico-sdk/sdk/2.3.1
PICO_TOOLCHAIN_PATH ?= $(HOME)/.pico-sdk/toolchain/15_2_Rel1
PICO_BUILD ?= local/firmware-build
# Host compiler for picotool, which the SDK builds; plain cc is not always one.
PICO_HOST_CC ?= clang

.PHONY: test firmware sim breadboard docs verify pico flash plot clean

test:
	$(PYTHON) -m pytest

firmware:
	$(PYTHON) -m pytest util/tests/test_firmware.py

sim:
	$(PYTHON) -m util.simulate

breadboard:
	$(PYTHON) -m util.breadboard

docs: sim breadboard

verify: test docs

pico:
	CC=$(PICO_HOST_CC) CXX=$(PICO_HOST_CC)++ cmake -S firmware -B $(PICO_BUILD) -G Ninja \
		-DPICO_SDK_PATH=$(PICO_SDK_PATH) -DPICO_TOOLCHAIN_PATH=$(PICO_TOOLCHAIN_PATH)
	CC=$(PICO_HOST_CC) CXX=$(PICO_HOST_CC)++ cmake --build $(PICO_BUILD)

$(BENCH_STAMP): pyproject.toml
	test -x $(BENCH_PYTHON) || $(PYTHON) -m venv $(VENV)
	$(BENCH_PYTHON) -m pip install --quiet -e '.[test,bench]'
	touch $@

flash: pico $(BENCH_STAMP)
	$(BENCH_PYTHON) -m util.flash $(PICO_BUILD)/PicoProgramECE455.uf2

plot: $(BENCH_STAMP)
	$(BENCH_PYTHON) firmware/adc_plots.py

clean:
	rm -rf .pytest_cache build *.egg-info
	find local -depth -mindepth 1 ! -path local/.gitkeep -delete
