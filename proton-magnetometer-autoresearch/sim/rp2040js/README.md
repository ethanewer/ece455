# C4: rp2040js emulator plumbing check

`node run_fid_est.js <image.bin> [truth_hz]`

1. `make -C firmware/targets/rp2040 ARM_GCC=<toolchain>/bin/ test`
   cross-compiles the byte-identical `firmware/core/freq_est.c` for
   Cortex-M0+ (SRAM-resident, no boot2 -- the runner starts the core
   from the image's vector table) and runs this runner.
2. The firmware pushes the FID record (generated from
   `tools/export_fid_vector.py`, seed 4242) through `freq_est_f32`
   and prints `FREQ_MHZ=<integer milli-Hz>` over UART0.
3. The runner asserts the reported frequency within 0.5 Hz of truth.

Setup: `npm install rp2040js` in this directory (MIT, local, no quota).

Explicitly NOT a timing/sensitivity oracle: rp2040js is functional, not
cycle-accurate -- this proves samples move through the firmware
estimator, nothing about clock accuracy or jitter.
