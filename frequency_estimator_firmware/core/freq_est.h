/*
 * freq_est.h -- portable FID frequency estimator core (C1).
 *
 * The baseline is an exponentially weighted zoom matched filter with a
 * coarse seed, NCO mix to baseband, FIR decimator, residual-frequency scan,
 * and log-parabolic refinement. It is portable C99 with no vendor headers
 * or dynamic allocation.
 *
 * Numeric mode (one compile switch, CI tests BOTH per the MCU research doc):
 *   - default         : float32 signal path (Cortex-M4F/M7 class)
 *   - -DFE_FIXED_POINT: int32 (Q31) signal path, 64-bit accumulators and a
 *     Q31 table NCO (Cortex-M0+ class, no FPU)
 *
 * Host tests compile this same source. Clock error, comparator time walk, and
 * other analog effects belong in signal generation or hardware tests, not in
 * this estimator.
 *
 * Workspace is static: no malloc. Input records longer than FE_MAX_N
 * return FE_ERR_INPUT (a real port streams; this core is sized for a 1.5 s
 * record of about 1.09 s at the active 30 kS/s rate plus margin).
 */
#ifndef FREQ_EST_H
#define FREQ_EST_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FE_OK          0
#define FE_ERR_INPUT   (-1)   /* n out of range */
#define FE_ERR_SEED    (-2)   /* no usable coarse seed in band */

/* Tunables mirroring the Python zoom_fit defaults. */
#define FE_DEC         10     /* FIR decimation factor                    */
#define FE_FIR_TAPS    33     /* FIR lowpass length (odd)                 */
#define FE_SPAN_HZ     20.0   /* residual scan half-span [Hz]             */
#define FE_STEP_HZ     0.02   /* residual grid step [Hz]                  */
#ifndef FE_SEED_WINDOW
#define FE_SEED_WINDOW 8192
#endif   /* coarse-seed window [samples]             */
#define FE_MAX_N       (FE_SEED_WINDOW * 4)   /* 32768 samples max  */

/*
 * freq_est_f32 -- estimate the FID frequency from ADC-domain samples.
 *
 *   v          : samples (front-end gain included, quantization included)
 *   n          : number of samples (512..FE_MAX_N)
 *   fs         : sample rate [Hz]
 *   t0         : time of v[0] since FID start [s] (the blanking time)
 *   f_lo,f_hi  : search band [Hz] (the AFE passband)
 *   out_hz     : estimate [Hz]
 *
 * Returns FE_OK or a negative error code.
 */
int freq_est_f32(const float *v, int n, double fs, double t0,
                 double f_lo, double f_hi, double *out_hz);

/* Fixed-point variant: Q31 samples (v_q31 = v/full_scale * 2^31), same
 * algorithm through the Q31 path. Returns the same codes. */
int freq_est_fixed(const int32_t *v, int n, double fs, double t0,
                   double f_lo, double f_hi, double *out_hz);

/* Exposed for host unit tests: one point of the weighted zoom spectrum
 * S(df) = |sum_k w_k z_k e^{-j2 pi df t_k}|^2 (float path). */
void fe_zoom_point_f32(const float *zre, const float *zim, const float *w,
                       int m, double tb0, double dtb, double df,
                       double *s_out);

/* Alternative estimator implementations used for comparison tests.
 * They are float-only and are not the baseline, so no Q31 port is provided.
 *
 * fft_est_f32 -- zero-padded FFT magnitude peak + log-parabolic refine.
 * zc_est_f32  -- interpolated rising-edge crossings + slope-weighted mean
 *                period, cycle-slip-filtered against the FFT peak (RULED
 *                OUT at FID SNRs; kept so the ruling-out is scored E2E).
 * Both return FE_OK or a negative error code (the binding maps errors to
 * NaN, i.e. a gross error). */
int fft_est_f32(const float *v, int n, double fs, double t0,
                double f_lo, double f_hi, double *out_hz);
int zc_est_f32(const float *v, int n, double fs, double t0,
               double f_lo, double f_hi, double *out_hz);

#ifdef __cplusplus
}
#endif
#endif /* FREQ_EST_H */
