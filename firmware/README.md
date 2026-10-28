# Pico 2 firmware

Copied from [hjvania10-rgb/PicoProgramECE455](https://github.com/hjvania10-rgb/PicoProgramECE455) at commit `3450aba` (2026-10-28), without that repository's superseded variants (`PicoProgramECE455_WIthoutButtons.c`, `PicoProgramECE455_WIthButtonsWithoutBetterPlots.c`, `adc_plots_old.py`). Two local changes: the ready prompt prints the start button's actual pin, and `adc_plots.py` finds the Pico's serial port by itself. Keep this folder in step with that repository. Its ADS1256 datasheet is in [`../docs/datasheets/`](../docs/datasheets/).

`PicoProgramECE455.c` configures the ADS1256 over SPI0 (GP16 DOUT, GP17 CS, GP18 SCLK, GP19 DIN, GP20 DRDY), then waits for the start button (SW3, GP27). Each press:

1. drives GP0 high for 8 s to polarize (GP0 is J7 pin 3 on the signal board);
2. waits 50 ms;
3. captures at 15 kSPS until the signal falls to 10 % of its first 100 ms, or 3 s pass;
4. fits the frequency from zero crossings and adds an empirical +0.05 Hz correction;
5. prints the results and sends the whole record in binary over USB serial.

Presses are accepted at most every 10 s. `adc_plots.py` receives each record and plots the whole capture and its 100–150 ms window, with the frequency and field.

## Build, flash, and plot

```sh
make pico     # build local/firmware-build/PicoProgramECE455.uf2
make flash    # build, reboot the Pico into BOOTSEL over USB, and copy the image
make plot     # run adc_plots.py
```

These need the Pico SDK 2.3.1 and Arm toolchain 15.2 under `~/.pico-sdk/` (where the Raspberry Pi Pico VS Code extension installs them; override `PICO_SDK_PATH` and `PICO_TOOLCHAIN_PATH` otherwise), CMake, Ninja, and `pip install -e '.[bench]'` for `pyserial`. `make flash` cannot open the port while the plotter has it; stop the plotter first. A Pico with no running firmware needs BOOTSEL held while plugging it in.

## Host tests

`make firmware` compiles `PicoProgramECE455.c` unchanged against stub SDK headers (`util/firmware_host/`) and runs its frequency estimator on synthetic FIDs. Run it after changing the estimator.
