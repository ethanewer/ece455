# Pico 2 firmware

Copied from [hjvania10-rgb/PicoProgramECE455](https://github.com/hjvania10-rgb/PicoProgramECE455) at commit `e9b393a` (2026-09-30). Keep this folder in step with that repository. Its ADS1256 datasheet is in [`../docs/datasheets/`](../docs/datasheets/).

- `PicoProgramECE455.c` configures the ADS1256 over SPI0 (GP16 DOUT, GP17 CS, GP18 SCLK, GP19 DIN, GP20 DRDY), captures until the FID decays to 10 % or 4 s pass, and fits the frequency from zero crossings. It prints the results and sends the first 10 ms of samples over USB serial.
- `adc_plots.py` reads that serial stream and plots each capture with its frequency and field. Set `PORT` to the Pico's serial port first; it needs `pyserial` and `matplotlib`.

## Build

Build with the Raspberry Pi Pico VS Code extension, which installs the SDK 2.3.1 and Arm toolchain 15.2 that `CMakeLists.txt` and `.vscode/` name. A plain CMake build needs the SDK and `arm-none-eabi-gcc` on `PATH`:

```sh
cmake -S firmware -B local/firmware-build -DPICO_SDK_PATH=/path/to/pico-sdk
cmake --build local/firmware-build
```

Then copy `local/firmware-build/PicoProgramECE455.uf2` to the Pico in BOOTSEL mode.

## Host tests

`make firmware` compiles `PicoProgramECE455.c` unchanged against stub SDK headers (`util/firmware_host/`) and runs its frequency estimator on synthetic FIDs. Run it after changing the estimator.
