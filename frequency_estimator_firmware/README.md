# Frequency estimator

`core/` is a portable C99 estimator with floating-point and Q31 builds. `host/vectors/` contains 36 hash-pinned synthetic ADC records over three frequencies, three decay constants, and four SNR levels. `make firmware` compiles the core, compares its output with `host/freq_est_mirror.py`, and runs the maximum-record fixed-point path under address and undefined-behavior sanitizers.

These vectors test estimator implementation and numeric portability. They do not include the active receiver transfer function and are not a hardware sensitivity claim. Validate the full receiver with the calibrated injections in `docs/verification-plan.md`.
