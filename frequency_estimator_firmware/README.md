# Frequency estimator

`core/` is a portable C99 estimator with floating-point and Q31 builds. `host/vectors/` contains 36 hash-pinned synthetic ADC records over three frequencies, three decay constants, and four SNR levels, each 1.5 s at 30 kSPS. `make firmware` compiles the core, compares its output with `host/freq_est_mirror.py`, and runs the maximum-record fixed-point path under address and undefined-behavior sanitizers.

The production estimator keeps only the decimated envelope, not a second copy of the full-rate record. `fft_est.c` and `zc_est.c` are comparison paths and do not allocate multi-megabyte transforms, so the whole `core/` directory can be linked into the XIAO RP2350 image. A zoom peak on either end of the ±20 Hz grid returns `FE_ERR_SEED` instead of a frequency.

These vectors test estimator implementation and numeric portability. Their noise is uniform from 500 to 3500 Hz, so it covers every carrier in the set, and the labeled SNR is 20 log10(V0/sigma) of that noise. They do not include the active receiver transfer function and are not a hardware sensitivity claim. Validate the full receiver with the calibrated injections in `docs/verification-plan.md`.
