# Research: evaluating the MCU/firmware stack for sensitivity

> How to score a firmware+MCU design for FID frequency-measurement
> sensitivity (<0.04 Hz on ~2 kHz over 1–3 s ≈ 20 ppm relative) without
> hardware-in-the-loop. Compiled February 2026.

## 1. ppm → nT math (the acceptance numbers everything hangs on)

γp/2π = 42.577478 MHz/T ⇒ f = 42.577478e6·B, so **relative frequency error
maps 1:1 to relative field error**:

| Field B | FID frequency | 1 ppm | 20 ppm (0.04 Hz @ 2 kHz) | ±0.5 ppm TCXO | ±2 ppm TCXO | ±20 ppm crystal |
|---|---|---|---|---|---|---|
| 25 µT | 1064.4 Hz | 0.025 nT | 0.5 nT | 0.0125 nT | 0.05 nT | 0.5 nT |
| 50 µT | 2132.9 Hz | 0.05 nT | 1.0 nT | 0.025 nT | 0.1 nT | 1.0 nT |
| 65 µT | 2767.5 Hz | 0.065 nT | 1.3 nT | 0.0325 nT | 0.13 nT | 1.3 nT |

- The 0.04 Hz requirement ≈ 20 ppm ≈ ~1 nT — the normal spec for a good PPM.
- A ±20 ppm plain crystal contributes up to 0.04 Hz **by itself** — zero
  margin. ±0.5–2 ppm TCXO leaves 10–40× margin. Published practice: GEM states
  observatory proton magnetometers use TCXO/ovenized crystals (~1 ppm/yr) to
  reach <0.05 nT; JPM-4 uses a 4 MHz TCXO with 2 ppm accuracy
  ([GEM Systems PDF](https://www.gemsys.ca/pdf/Requirements_for_Obtaining_High_Accuracy_with_Proton_Magnetometers.pdf),
  [JPM-4](https://sensors.myu-group.co.jp/sm_pdf/SM2789.pdf)).
- **RP2040 caveat:** XOSC accuracy is set by the external crystal (Pico board
  crystal ~±30–50 ppm class; ROSC is ±10–40% and unusable as reference).
  RP2040 datasheet §2.15–2.17:
  [rp2040-datasheet.pdf](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf).
  The SDK exposes an internal frequency counter (`frequency_count_khz()`,
  ±1 kHz) usable to measure your own clock against a known signal.

### Capture jitter vs reference error (why jitter is a non-issue)

Edge timestamps `t_k = t₀ + kT + ε_k`, jitter σ_ε:
- Average-period estimator: σ_f/f ≈ √2·σ_ε/T_record. σ_ε = 1 cycle = 8 ns
  @125 MHz, T_record = 2 s → **5.7e-9 relative (~0.006 ppm)** ≈ 1e-5 Hz @2 kHz.
- Full LSQ phase/period regression over M ≈ 4000 edges:
  σ_f = σ_ε·√(12/M)/T_record ≈ 2e-10 Hz.

So ±1-cycle PIO/timer capture jitter is ~4 orders below the 0.04 Hz budget
and ~3 orders below the TCXO's contribution. The real analog-side threat is
**comparator time-walk** (zero-crossing shift ≈ V_noise/(2πfA), growing as the
FID decays) — a *systematic* bias, not jitter; model it in synthetic tests,
don't try to measure it on emulators.

## 2. Comparison table: three testing layers

| | **Native unit test** | **Emulator / FW-in-the-loop** (Renode, Wokwi/rp2040js, QEMU) | **HIL bench** |
|---|---|---|---|
| What runs | portable C estimator + synthetic FID vectors | real firmware binary on instruction-level CPU + register models | real silicon, real clocks, real AFE |
| Catches | estimator bias/variance, SNR robustness, **modeled time-walk bias**, fixed-point overflow/rounding, decay handling, missing/duplicate edges, float-vs-Q31 drift, regressions vs golden vectors | register/driver bugs, DMA/PIO/timer config, ISR flow, timestamp pipeline, buffer races, boot/UF2, serial protocol | actual ISR latency jitter, DMA/PIO behavior, TCXO ppm, analog time-walk, temperature, PSU noise, EMI |
| Doesn't catch | HAL/register config, interrupt latency, DMA races, clock tree | **timing accuracy** (Renode functional, not cycle-accurate — [issue #244](https://github.com/renode/renode/issues/244), [#445](https://github.com/renode/renode/issues/445)); Wokwi rp2040js: PIO functional, single-core; QEMU raspi-pico RFC: **no PIO** | cost, determinism, CI-friendliness |
| Setup cost | **Low** (GCC + pytest/Ceedling, free CI) | Low–medium (Wokwi easiest but cloud-metered; Renode medium) | High (board, GPSDO/TCXO reference, $10 fx2 LA) |
| CI maturity | excellent (JUnit, gcov, Docker) | good for Renode (official GH Action, Robot Framework); Wokwi alpha + 50 min/mo free | self-hosted only |
| Verdict | **Primary — sensitivity scoring happens here** | Secondary — validates plumbing logically, not temporally | final acceptance + clock calibration |

Crucial design consequence: **frequency-measurement sensitivity is a property
of the estimator + clock reference, not of the MCU.** Score designs numerically
in CI (native estimator over a synthetic FID matrix, timestamps quantized at
each candidate MCU's capture resolution, each candidate clock's ppm injected);
emulators only prove the plumbing moves timestamps.

## 3. Renode / Wokwi / QEMU specifics

### Renode (MIT, Antmicro) — best for STM32
- Boards: STM32F4/F7 Discovery, F103 BluePill, Nucleo; CPU-level `stm32f429`,
  `stm32h743`, `nucleo_f767zi`; NXP i.MX RT1064 EVK (the RT1062 in a Teensy
  4.1) — [supported boards](https://renode.readthedocs.io/en/latest/introduction/supported-boards.html).
  Teensy 4.1 board file = open [PR #651](https://github.com/renode/renode/pull/651).
- **RP2040 not mainline** ([issue #262](https://github.com/renode/renode/issues/262));
  community fork [matgla/Renode_RP2040](https://github.com/matgla/Renode_RP2040)
  (Renode 1.16.1; DMA/GPIO/PLL, partial PIO via external C++ sim, ADC, timers).
- **Injecting a 2 kHz square wave:** GPIO `Miscellaneous.Button` + `gpio.button
  Toggle`, or `OnGPIO(pin,state)` from Monitor Python
  ([testing API](https://renode.readthedocs.io/en/latest/basic/renode-testing-api.html));
  programmatic edge trains via External Control server `GPIOPort SetState`.
  ADC: **RESD files** (`FeedSamplesFromRESD`) — generate the decaying-sinusoid
  FID offline in Python, stream it ([RESD docs](https://renode.readthedocs.io/en/latest/basic/resd.html),
  [Antmicro RESD blog](https://antmicro.com/blog/2022/12/synchronized-multi-sensor-data-in-renode-with-resd)).
  Arbitrary peripherals: `Python.PythonPeripheral`.
- **Critical caveat:** functional simulator — peripheral timing "happens
  instantly", CPU speed is a tuning knob ([time framework](https://renode.readthedocs.io/en/latest/advanced/time_framework.html),
  [#244](https://github.com/renode/renode/issues/244), [#445](https://github.com/renode/renode/issues/445),
  STM32 timer off-by-one [#613](https://github.com/renode/renode/issues/613)).
  A Renode frequency measurement will not predict real jitter/ISR latency.
- CI: Robot Framework built in — `renode-test test.robot` ([testing docs](https://renode.readthedocs.io/en/latest/introduction/testing.html));
  official [`antmicro/renode-test-action@v5`](https://github.com/antmicro/renode-test-action);
  [Memfault walkthrough](https://interrupt.memfault.com/blog/test-automation-renode);
  [PlatformIO+Renode](https://docs.platformio.org/en/latest/advanced/unit-testing/simulators/renode.html).

### Wokwi (rp2040js) — best for RP2040
- Simulates RP2040 **including PIO (with debugger) and DMA-for-PIO**, GPIO/
  UART/I2C/SPI/PWM, ADC; single core only ([wokwi-pi-pico](https://docs.wokwi.com/parts/wokwi-pi-pico)).
  Underlying emulator MIT-licensed [wokwi/rp2040js](https://github.com/wokwi/rp2040js) —
  headless in Node with GDB server (port 3333); no cloud quota needed locally.
- CLI/CI: `wokwi-cli` (`--elf --timeout --expect-text --fail-text
  --serial-log-file --vcd-file`); scenario YAML alpha ([getting started](https://docs.wokwi.com/wokwi-ci/getting-started),
  [scenarios](https://docs.wokwi.com/wokwi-ci/automation-scenarios),
  [GH Action](https://docs.wokwi.com/wokwi-ci/github-actions)).
  **Quota: 50 simulation-minutes/month free**, cloud-executed.
- **Injecting the square wave:** scenario YAML cannot drive pins; use the
  **Custom Chips API** (C→WASM or Rust): a ~30-line "FID generator" chip
  toggling a pin via timer callback ([chips API](https://docs.wokwi.com/chips-api/getting-started),
  [GPIO API](https://docs.wokwi.com/chips-api/gpio)). Built-in 8-channel logic
  analyzer exports VCD for PulseView/GTKWave.

### QEMU
- **No RP2040, no STM32 machine mainline.** `raspi-pico` exists only as an
  unmerged RFC (2026): no PIO/ADC/SPI/I2C/PWM
  ([RFC cover](https://lists.nongnu.org/archive/html/qemu-devel/2026-08/msg08141.html)).
  STM32 only via forks (beckus/qemu_stm32). Verdict: dead end for PIO-counting
  firmware; RP2040 → rp2040js/Wokwi, STM32 → Renode.

## 4. Native (host) testing of the DSP core

- **Ceedling + Unity + CMock** ([docs](https://throwtheswitch.github.io/Ceedling/latest/)):
  `ceedling test:all` with GCC, gcov, JUnit XML, CI Docker images;
  CI example: [Embedded Artistry](https://embeddedartistry.com/blog/2019/02/25/unit-testing-and-reporting-on-a-build-server-using-ceedling-and-unity/)
- **PlatformIO Unity**: same tests `native` + on-target
  ([docs](https://docs.platformio.org/en/latest/advanced/unit-testing/frameworks/unity.html))
- Or **pytest + ctypes/cffi** against a host-built `libestimator.so` — lets
  Python drive the parameter sweep (this pipeline's choice).
- **CMSIS-DSP builds on host** (`-DHOST=ON`) with a `pip install cmsisdsp`
  NumPy wrapper — the precedent for same-DSP-code-on-host-and-target:
  [ARM-software/CMSIS-DSP](https://github.com/ARM-software/CMSIS-DSP/)

**Scoring matrix (CI):** FID at 1064/2133/2767 Hz; T2* 0.3–3 s; SNR sweep;
zero-crossing timestamps quantized at 5.9 ns (STM32 G4), 6.7 ns (Teensy 4.1),
8 ns (RP2040 PIO @125 MHz); modeled comparator time-walk; missing edges; TCXO
ppm offsets (0.5/2/20 ppm) as deterministic gain error; harmonic + 50/60 Hz
pickup. Metrics: σ_f, bias; gate 0.04 Hz.

**Fixed-point vs float per core:**
- **M0+ (RP2040)** — no FPU: soft-float only. Integers natural (timestamps are
  integers): 64-bit fixed-point phase accumulator + integer period regression.
  ST AN4841: Q31 ≈ Q15 on M0; float FFTs dramatically slower than M4F
  ([ST AN4841](https://www.st.com/resource/en/application_note/an4841-digital-signal-processing-for-stm32-microcontrollers-using-cmsis-stmicroelectronics.pdf))
- **M4F/M7** — hardware FPU: float (CMSIS-DSP `arm_rfft_fast_f32`) ≈ Q31 cost;
  Q15 ~2× faster on M4 via SIMD ([Silabs AN0051](https://www.silabs.com/documents/public/application-notes/AN0051.pdf)).
  No compute wall for a 1–3 kHz record (4096-pt FFT sub-ms on M4) → favor f32
  on M4F/M7, 64-bit int on M0+; single estimator source with a numeric-mode
  compile switch, CI-test both (catches Q31 headroom bugs).

## 5. RP2040 capture facts

- **RP2040 has no hardware input-capture unit** — Cornell ECE4760 implements
  it with two phase-locked PIO SMs, timestamping to **±1 system clock (8 ns)**
  with DMA-fed 32/64-bit timestamps
  ([Cornell page](https://people.ece.cornell.edu/land/courses/ece4760/RP2040/C_SDK_PIO_control/Input_capture/index_pio_control.html))
- Production-grade open implementations: DMA-snapshotting the µs timer per edge
  (reciprocal counting) ([PicoFreq / iosoft.blog](https://iosoft.blog/2023/07/30/picofreq/));
  PIO pulse counting with recursive DMA chaining + second SM latching the count
  on a gate edge (~8 ns latch latency) ([rp2040-freq-counter](https://github.com/richardjkendall/rp2040-freq-counter));
  generic PIO capture ~0.07 µs ([dgatf](https://github.com/dgatf/Pio-Pin-Capture-Timer-for-RP2040))
- STM32 G4/F4 and iMXRT1062 Quad Timer have true hardware input capture
  (~5.9–6.7 ns) — irrelevant at this accuracy, but simpler than PIO.
- Budget roll-up at 50 µT, 2 s record: capture jitter → ~1e-5 Hz; ±0.5 ppm
  TCXO → 1.1 mHz; ±20 ppm crystal → 43 mHz (fails); estimator noise floor with
  SNR ≥ 10 dB + full regression → <0.5 mHz. **Design rule: TCXO mandatory;
  estimator must be regression-based, not single-edge.**

## 6. Bench/HIL validation and CI patterns

- **sigrok/PulseView + $10 fx2lafw LA**: scriptable headless capture
  (`sigrok-cli -d fx2lafw --config samplerate=24m --samples 10M -O csv`)
  ([fx2lafw](https://sigrok.org/wiki/Fx2lafw), [getting started](https://sigrok.org/wiki/Getting_started_with_a_logic_analyzer),
  [SparkFun tutorial](https://learn.sparkfun.com/tutorials/using-the-usb-logic-analyzer-with-sigrok-pulseview))
- **Reference injection:** generator disciplined by GPS 1PPS; open GPSDOs:
  [felixd/STM32-GPSDO](https://github.com/felixd/STM32-GPSDO) (~€35, GPL-3.0),
  [GPSDO-YT](https://github.com/YannickTurcotte/GPSDO-YT),
  [ProtonFox/PF-GPSDO](https://gitlab.com/ProtonFox/pf-gpsdo) (RP2040);
  GEM describes GPS-locking magnetometer time bases
  ([GEM PDF](https://www.gemsys.ca/pdf/Requirements_for_Obtaining_High_Accuracy_with_Proton_Magnetometers.pdf))
- Frameworks: Pico SDK ships `picotest`; pico-sdk testing infra
  ([deepwiki](https://deepwiki.com/raspberrypi/pico-sdk/8-testing-infrastructure));
  DI + CMake `IS_PICO` dual-build pattern ([khurd21](https://khurd21.github.io/posts/unit-testing-embedded-software/))

**CI wiring (one repo, four jobs):**
1. `native-tests` — GCC build of `core/`, pytest/ceedling, gcov — always, <1 min
2. `emulator-tests` — `antmicro/renode-test-action@v5` (GPIO edge injection +
   `Wait For Line On Uart` asserting reported frequency); optional rp2040js/Wokwi
   (mind the 50 min/mo free cap; run rp2040js locally for unlimited)
3. `firmware-build` — PlatformIO matrix (`pio run`) across rp2040/stm32/teensy;
   `pio test -e native` reuses the same Unity tests
4. `sensitivity-score` — regenerate synthetic FID vectors, run the estimator
   (host build) with per-MCU timestamp quantization + per-clock ppm, emit
   σ_f/bias JSON, gate on 0.0426 Hz. The only job that needs a "score".

## 7. Recommended layered architecture

```
fid-mag/
├── core/            # 100% portable C99, NO HAL includes
│   ├── freq_est.c        # regression/phase fit; float32 & Q31(64-bit int) builds
│   ├── fid_model.c       # shared decaying-sinusoid model (used by tests)
│   └── test/             # Unity/pytest golden vectors: sensitivity matrix HERE
├── hal/                  # thin interfaces only
│   ├── time_source.h     # tick rate, get_ticks()
│   ├── capture.h         # edge_timestamp_stream() (comparator path)
│   └── adc.h             # sample_stream() (ADC path)
├── targets/
│   ├── rp2040/           # PIO timestamping SM + DMA (Cornell/PicoFreq pattern)
│   ├── stm32f4/          # timer input capture + DMA
│   └── teensy41/         # Quad Timer capture
├── sim/
│   ├── renode/  (.repl/.resc + .resd FID stream + .robot tests)
│   └── wokwi/   (fid_gen custom chip driving zero-crossings + LA VCD)
├── tools/
│   └── gen_fid.py        # synthetic FID + time-walk + ppm clock + quantization
└── ci/                   # native | renode | build | sensitivity-score
```

Rules: `core/` never includes vendor headers; `targets/` may include `core/`,
never vice versa; the timestamp→frequency contract is a single pure function
`freq_est(const edge_ts*, n, tick_hz, out_hz)`, so the CI sensitivity score
exercises byte-identical code to what ships; every analog effect emulators
can't reproduce (comparator time-walk, clock ppm) is a model in `gen_fid.py`.

**Bottom line:** the sensitivity grade comes from native estimator tests with
modeled clock error and time-walk; Renode is the best FW-in-the-loop option
for STM32 (MIT, Robot Framework CI, RESD/GPIO injection) with rp2040js/Wokwi
as the PIO-capable RP2040 option; QEMU is a dead end for RP2040; and a
±0.5–2 ppm TCXO is the single hardware decision that most affects the
0.04 Hz target.
