/*
 * freq_est.c -- portable FID frequency estimator core (C1).
 *
 * Spec-level mirror of poc/estimators.py::zoom_fit; a numpy mirror of THIS
 * algorithm lives in tools/freq_est_mirror.py, and the two are
 * cross-validated on the same golden vectors in the firmware host tests.
 *
 * Pipeline:
 *   1. mean removal;
 *   2. coarse seed: Goertzel scan of |X(f)|^2 over [f_lo, f_hi] on the
 *      first FE_SEED_WINDOW samples (bin = fs/window), log-parabolic
 *      refine. (The Python zoom_fit seeds from a zero-padded FFT peak over
 *      the whole record; both are "coarse seed inside the zoom span",
 *      which is all the zoom stage requires.)
 *   3. NCO mix to baseband at the seed: z[k] = x[k] e^{-j2 pi f0 t[k]};
 *   4. windowed-sinc FIR lowpass (cutoff fs/(2*FE_DEC), Hamming window,
 *      DC gain exactly 1) + decimate by FE_DEC -> complex envelope z_b;
 *   5. tau from block maxima of |z_b| (m/256 blocks), amplitude-gated log
 *      fit down to 0.5 of peak, clipped to [0.1, 20] s -- the analog of
 *      estimators._estimate_tau on the true complex envelope;
 *   6. weighted zoom: S(df) = |sum_k w_k z_b[k] e^{-j2 pi df t_b[k]}|^2
 *      with w = exp(-t_b/tau) over +/-FE_SPAN_HZ at FE_STEP_HZ;
 *      log-parabolic refine.
 *
 * Numeric modes (one compile switch; CI tests both on the same vectors):
 *   default          : float32 signal path (M4F/M7 class)
 *   -DFE_FIXED_POINT : Q31 signal path, int64 accumulators, table NCO
 *                      (M0+ class, no FPU)
 */
#include "freq_est.h"

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define FE_NGRID   2001                       /* 2*20/0.02 + 1 */
#define FE_OUT_MAX (FE_MAX_N / FE_DEC)

static double fir[FE_FIR_TAPS];

static void fe_fir_init(double fs)
{
    /* Hamming-windowed sinc, cutoff fs/(2*FE_DEC), DC gain exactly 1. */
    int mid = (FE_FIR_TAPS - 1) / 2;
    double fc = fs / (2.0 * FE_DEC);
    double sum = 0.0;
    for (int i = 0; i < FE_FIR_TAPS; i++) {
        int k = i - mid;
        double xx = M_PI * (double)k * 2.0 * fc / fs;
        double sinc = (k == 0) ? 1.0 : sin(xx) / xx;
        double win = 0.54 - 0.46
                     * cos(2.0 * M_PI * (double)i / (double)(FE_FIR_TAPS - 1));
        fir[i] = (2.0 * fc / fs) * sinc * win;
        sum += fir[i];
    }
    for (int i = 0; i < FE_FIR_TAPS; i++) {
        fir[i] /= sum;
    }
}

static double fe_log_parabolic(const double *s, int k)
{
    double a = log(s[k - 1] > 0.0 ? s[k - 1] : 1e-300);
    double b = log(s[k] > 0.0 ? s[k] : 1e-300);
    double c = log(s[k + 1] > 0.0 ? s[k + 1] : 1e-300);
    double den = a - 2.0 * b + c;
    if (den == 0.0) {
        return 0.0;
    }
    double d = 0.5 * (a - c) / den;
    if (d > 1.0) {
        d = 1.0;
    } else if (d < -1.0) {
        d = -1.0;
    }
    return d;
}

/* ================================================================== */
/* float32 mode                                                        */
/* ================================================================== */
#ifndef FE_FIXED_POINT

void fe_zoom_point_f32(const float *zre, const float *zim, const float *w,
                       int m, double tb0, double dtb, double df,
                       double *s_out)
{
    double e_re = cos(-2.0 * M_PI * df * tb0);
    double e_im = sin(-2.0 * M_PI * df * tb0);
    double d_re = cos(-2.0 * M_PI * df * dtb);
    double d_im = sin(-2.0 * M_PI * df * dtb);
    double sr = 0.0, si = 0.0;
    for (int k = 0; k < m; k++) {
        double zr = (double)zre[k], zi = (double)zim[k], wk = (double)w[k];
        sr += wk * (zr * e_re - zi * e_im);
        si += wk * (zr * e_im + zi * e_re);
        double n_re = e_re * d_re - e_im * d_im;
        e_im = e_re * d_im + e_im * d_re;
        e_re = n_re;
    }
    *s_out = sr * sr + si * si;
}

/* tau from block maxima of the complex envelope (dtb = decimated dt).
 * blk = m/256 -> n_blk ~ 256 blocks for any m (bugbot: the env buffer must
 * hold the block count, which is bounded by ~257, not by FE_OUT_MAX/16). */
static double fe_tau_from_envelope_f32(const float *zre, const float *zim,
                                       int m, double dtb)
{
    static double env[FE_OUT_MAX / 12 + 4];   /* >= n_blk for all m */
    int blk = m / 256;
    int n_blk = blk > 0 ? m / blk : 0;
    if (n_blk < 8 || n_blk > (int)(sizeof(env) / sizeof(env[0]))) {
        return 1.0;
    }
    for (int b = 0; b < n_blk; b++) {
        double e = 0.0;
        for (int j = 0; j < blk; j++) {
            int k = b * blk + j;
            double mag = sqrt((double)zre[k] * zre[k]
                              + (double)zim[k] * zim[k]);
            if (mag > e) {
                e = mag;
            }
        }
        env[b] = e;
    }
    double mx = env[0];
    for (int b = 1; b < n_blk; b++) {
        if (env[b] > mx) {
            mx = env[b];
        }
    }
    if (!(mx > 0.0)) {
        return 1.0;
    }
    int end = n_blk;
    for (int b = 0; b < n_blk; b++) {
        if (env[b] < 0.5 * mx) {
            end = b;
            break;
        }
    }
    if (end < 8) {
        return 1.0;
    }
    double sx = 0.0, sy = 0.0, sxx = 0.0, sxy = 0.0;
    for (int b = 0; b < end; b++) {
        double t = (b + 0.5) * (double)blk * dtb;
        double y = log(env[b] > 0.0 ? env[b] : 1e-300);
        sx += t;
        sy += y;
        sxx += t * t;
        sxy += t * y;
    }
    double den = (double)end * sxx - sx * sx;
    if (den == 0.0) {
        return 1.0;
    }
    double slope = ((double)end * sxy - sx * sy) / den;
    if (slope >= 0.0) {
        return 1.0;
    }
    double tau = -1.0 / slope;
    if (tau < 0.1) {
        tau = 0.1;
    }
    if (tau > 20.0) {
        tau = 20.0;
    }
    return tau;
}

int freq_est_f32(const float *v, int n, double fs, double t0,
                 double f_lo, double f_hi, double *out_hz)
{
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    static float x[FE_MAX_N];
    static float zfre[FE_MAX_N], zfim[FE_MAX_N];
    static float zbre[FE_OUT_MAX], zbim[FE_OUT_MAX], w[FE_OUT_MAX];
    static double sgrid[FE_NGRID];

    /* 1. mean removal. */
    double mean = 0.0;
    for (int i = 0; i < n; i++) {
        mean += (double)v[i];
    }
    mean /= (double)n;
    for (int i = 0; i < n; i++) {
        x[i] = (float)((double)v[i] - mean);
    }

    /* 2. coarse seed: Goertzel scan + log-parabolic refine. */
    fe_fir_init(fs);
    int nseed = n < FE_SEED_WINDOW ? n : FE_SEED_WINDOW;
    double df_bin = fs / (double)nseed;
    int k_lo = (int)ceil(f_lo / df_bin);
    int k_hi = (int)floor(f_hi / df_bin);
    if (k_lo < 1 || k_hi <= k_lo + 1) {
        return FE_ERR_SEED;
    }
    double best = -1.0;
    int best_k = k_lo;
    for (int k = k_lo; k <= k_hi; k++) {
        double c1 = 2.0 * cos(2.0 * M_PI * (double)k / (double)nseed);
        double s1 = 0.0, s2 = 0.0;
        for (int i = 0; i < nseed; i++) {
            double s0 = (double)x[i] + c1 * s1 - s2;
            s2 = s1;
            s1 = s0;
        }
        double p = s1 * s1 + s2 * s2 - c1 * s1 * s2;
        if (p > best) {
            best = p;
            best_k = k;
        }
    }
    double f0;
    if (best_k == k_lo || best_k == k_hi) {
        f0 = (double)best_k * df_bin;          /* can't refine at the edge */
    } else {
        double s3[3];
        for (int q = 0; q < 3; q++) {
            double f = (double)(best_k + q - 1) * df_bin;
            double sr = 0.0, si = 0.0;
            for (int i = 0; i < nseed; i++) {
                double ang = -2.0 * M_PI * f * (double)i / fs;
                sr += (double)x[i] * cos(ang);
                si += (double)x[i] * sin(ang);
            }
            s3[q] = sr * sr + si * si;
        }
        f0 = (double)best_k * df_bin + fe_log_parabolic(s3, 1) * df_bin;
    }

    /* 3. NCO mix to baseband. */
    double e_re = cos(-2.0 * M_PI * f0 * t0);
    double e_im = sin(-2.0 * M_PI * f0 * t0);
    double d_re = cos(-2.0 * M_PI * f0 / fs);
    double d_im = sin(-2.0 * M_PI * f0 / fs);
    for (int i = 0; i < n; i++) {
        zfre[i] = (float)((double)x[i] * e_re);
        zfim[i] = (float)((double)x[i] * e_im);
        double n_re = e_re * d_re - e_im * d_im;
        e_im = e_re * d_im + e_im * d_re;
        e_re = n_re;
    }

    /* 4. FIR lowpass + decimate. */
    int m = 0;
    for (int k = 0; k + FE_FIR_TAPS <= n; k += FE_DEC) {
        double sr = 0.0, si = 0.0;
        for (int j = 0; j < FE_FIR_TAPS; j++) {
            sr += fir[j] * (double)zfre[k + j];
            si += fir[j] * (double)zfim[k + j];
        }
        zbre[m] = (float)sr;
        zbim[m] = (float)si;
        m++;
    }
    double dtb = (double)FE_DEC / fs;

    /* 5. tau from the complex envelope. */
    double tau = fe_tau_from_envelope_f32(zbre, zbim, m, dtb);

    /* 6. weighted zoom grid + parabolic refine. */
    for (int k = 0; k < m; k++) {
        w[k] = (float)exp(-(t0 + (double)k * dtb) / tau);
    }
    int ng = 0, best_g = 0;
    for (int g = 0; g < FE_NGRID; g++) {
        double dfc = -FE_SPAN_HZ + (double)g * FE_STEP_HZ;
        fe_zoom_point_f32(zbre, zbim, w, m, t0, dtb, dfc, &sgrid[g]);
        ng = g + 1;
        if (sgrid[g] > sgrid[best_g]) {
            best_g = g;
        }
    }
    if (best_g == 0 || best_g == ng - 1) {
        *out_hz = f0 - FE_SPAN_HZ + (double)best_g * FE_STEP_HZ;
        return FE_OK;
    }
    double d = fe_log_parabolic(sgrid, best_g);
    *out_hz = f0 + (-FE_SPAN_HZ + (double)best_g * FE_STEP_HZ)
              + d * FE_STEP_HZ;
    return FE_OK;
}

#else
/* ================================================================== */
/* 64-bit fixed-point mode (Q31 path, M0+ class, no FPU)               */
/* ================================================================== */

#define FE_NCO_BITS 12
#define FE_NCO_N    (1 << FE_NCO_BITS)
#define FE_FRAC     4294967296.0           /* 2^32: phase units per turn */

static int32_t nco_sin[FE_NCO_N + 1];
static int nco_ready = 0;

static void fe_nco_init(void)
{
    if (nco_ready) {
        return;
    }
    for (int i = 0; i <= FE_NCO_N; i++) {
        double q = sin(2.0 * M_PI * (double)i / (double)FE_NCO_N)
                   * 2147483647.0;
        nco_sin[i] = (int32_t)q;
    }
    nco_ready = 1;
}

/* cos/sin at phase (uint32 turns fraction), Q31 out, LUT + linear interp.
 * cos(x) = sin(x + pi/2): shift the index by N/4, same fractional bits. */
static void fe_nco_cossin(uint32_t ph, int32_t *c_out, int32_t *s_out)
{
    uint32_t idx = ph >> (32 - FE_NCO_BITS);
    uint32_t frac = (ph >> (32 - FE_NCO_BITS - 8)) & 0xFFu;
    int32_t a = nco_sin[idx];
    int32_t b = nco_sin[idx + 1];
    *s_out = (int32_t)(a + (((int64_t)(b - a) * (int64_t)frac) >> 8));
    uint32_t idxc = (idx + FE_NCO_N / 4) & (FE_NCO_N - 1);
    int32_t a2 = nco_sin[idxc];
    int32_t b2 = nco_sin[(idxc + 1) & (FE_NCO_N - 1)];
    *c_out = (int32_t)(a2 + (((int64_t)(b2 - a2) * (int64_t)frac) >> 8));
}

int freq_est_fixed(const int32_t *v, int n, double fs, double t0,
                   double f_lo, double f_hi, double *out_hz)
{
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    static int32_t x[FE_MAX_N];
    static int32_t zfre[FE_MAX_N], zfim[FE_MAX_N];
    static int32_t zbre[FE_OUT_MAX], zbim[FE_OUT_MAX], w[FE_OUT_MAX];
    static int32_t fir_q[FE_FIR_TAPS];
    static double env[FE_OUT_MAX / 16 + 2];
    static double sgrid[FE_NGRID];

    /* 1. mean removal (int64 running sum). */
    int64_t mean_acc = 0;
    for (int i = 0; i < n; i++) {
        mean_acc += v[i];
    }
    int32_t mean32 = (int32_t)(mean_acc / n);
    for (int i = 0; i < n; i++) {
        x[i] = v[i] - mean32;
    }

    /* 2. coarse seed: Goertzel on the leading window, computed in double
     * (once per record; the fixed-point requirement targets the streamed
     * signal path, per the MCU research doc's Q15 pattern). */
    fe_fir_init(fs);
    int nseed = n < FE_SEED_WINDOW ? n : FE_SEED_WINDOW;
    double df_bin = fs / (double)nseed;
    int k_lo = (int)ceil(f_lo / df_bin);
    int k_hi = (int)floor(f_hi / df_bin);
    if (k_lo < 1 || k_hi <= k_lo + 1) {
        return FE_ERR_SEED;
    }
    double best = -1.0;
    int best_k = k_lo;
    for (int k = k_lo; k <= k_hi; k++) {
        double c1 = 2.0 * cos(2.0 * M_PI * (double)k / (double)nseed);
        double s1 = 0.0, s2 = 0.0;
        for (int i = 0; i < nseed; i++) {
            double s0 = (double)x[i] + c1 * s1 - s2;
            s2 = s1;
            s1 = s0;
        }
        double p = s1 * s1 + s2 * s2 - c1 * s1 * s2;
        if (p > best) {
            best = p;
            best_k = k;
        }
    }
    double f0 = (double)best_k * df_bin;

    /* 3. NCO mix (table NCO, uint32 phase accumulator). */
    fe_nco_init();
    uint32_t ph = (uint32_t)((t0 * f0 - floor(t0 * f0)) * 4294967296.0);
    uint32_t dph = (uint32_t)(f0 / fs * FE_FRAC); /* (uint64)(f0 / fs * 2^32) */
    for (int i = 0; i < n; i++) {
        int32_t s, c;
        fe_nco_cossin(ph, &c, &s);
        zfre[i] = (int32_t)(((int64_t)x[i] * c) >> 31);
        zfim[i] = (int32_t)(-(((int64_t)x[i] * s) >> 31));
        ph += dph;
    }

    /* 4. FIR (Q31 coefficients) + decimate. */
    for (int j = 0; j < FE_FIR_TAPS; j++) {
        fir_q[j] = (int32_t)(fir[j] * 2147483647.0);
    }
    int m = 0;
    for (int k = 0; k + FE_FIR_TAPS <= n; k += FE_DEC) {
        int64_t sr = 0, si = 0;
        for (int j = 0; j < FE_FIR_TAPS; j++) {
            sr += (int64_t)fir_q[j] * zfre[k + j];
            si += (int64_t)fir_q[j] * zfim[k + j];
        }
        zbre[m] = (int32_t)(sr >> 31);
        zbim[m] = (int32_t)(si >> 31);
        m++;
    }

    /* 5. tau from block maxima of |z_b| (magnitudes in double of Q31). */
    int blk = m / 256;
    int n_blk = blk > 0 ? m / blk : 0;
    double tau = 1.0;
    if (n_blk >= 8) {
        for (int b = 0; b < n_blk; b++) {
            double e = 0.0;
            for (int j = 0; j < blk; j++) {
                int k = b * blk + j;
                double mag = sqrt((double)zbre[k] * zbre[k]
                                  + (double)zbim[k] * zbim[k]);
                if (mag > e) {
                    e = mag;
                }
            }
            env[b] = e;
        }
        double mx = env[0];
        for (int b = 1; b < n_blk; b++) {
            if (env[b] > mx) {
                mx = env[b];
            }
        }
        if (mx > 0.0) {
            int end = n_blk;
            for (int b = 0; b < n_blk; b++) {
                if (env[b] < 0.5 * mx) {
                    end = b;
                    break;
                }
            }
            if (end >= 8) {
                double sx = 0.0, sy = 0.0, sxx = 0.0, sxy = 0.0;
                for (int b = 0; b < end; b++) {
                    double t = (b + 0.5) * (double)blk * ((double)FE_DEC / fs);
                    double y = log(env[b] > 0.0 ? env[b] : 1e-300);
                    sx += t;
                    sy += y;
                    sxx += t * t;
                    sxy += t * y;
                }
                double den = (double)end * sxx - sx * sx;
                if (den != 0.0) {
                    double slope = ((double)end * sxy - sx * sy) / den;
                    if (slope < 0.0) {
                        tau = -1.0 / slope;
                        if (tau < 0.1) {
                            tau = 0.1;
                        }
                        if (tau > 20.0) {
                            tau = 20.0;
                        }
                    }
                }
            }
        }
    }

    /* 6. weighted zoom grid: Q31 weights, int64 accumulators. Per-term
     * scaling >>8 keeps products <= 2^46, safe to accumulate over m. */
    for (int k = 0; k < m; k++) {
        double wk = exp(-(t0 + (double)k * (double)FE_DEC / fs) / tau);
        w[k] = (int32_t)(wk * 2147483647.0);
    }
    int ng = 0, best_g = 0;
    for (int g = 0; g < FE_NGRID; g++) {
        double dfc = -FE_SPAN_HZ + (double)g * FE_STEP_HZ;
        /* Negative double -> uint32_t is UB; go through int64 (the
         * int64 -> uint32 conversion is well-defined modulo 2^32). */
        uint32_t phg = (uint32_t)(int64_t)(t0 * dfc * FE_FRAC);
        uint32_t dphg = (uint32_t)(int64_t)
                        (dfc * (double)FE_DEC / fs * FE_FRAC);
        int64_t sr = 0, si = 0;
        for (int k = 0; k < m; k++) {
            int32_t s, c;
            fe_nco_cossin(phg, &c, &s);
            int64_t pr = ((int64_t)zbre[k] * w[k]) >> 31;
            int64_t pi = ((int64_t)zbim[k] * w[k]) >> 31;
            /* S = sum w * z * e^{-j phi}: (pr + j pi)(c - j s) */
            sr += ((pr >> 8) * (c >> 8)) + ((pi >> 8) * (s >> 8));
            si += ((pi >> 8) * (c >> 8)) - ((pr >> 8) * (s >> 8));
            phg += dphg;
        }
        double ss = (double)sr * sr + (double)si * si;
        sgrid[g] = ss;
        ng = g + 1;
        if (ss > sgrid[best_g]) {
            best_g = g;
        }
    }
    if (best_g == 0 || best_g == ng - 1) {
        *out_hz = f0 - FE_SPAN_HZ + (double)best_g * FE_STEP_HZ;
        return FE_OK;
    }
    double d = fe_log_parabolic(sgrid, best_g);
    *out_hz = f0 + (-FE_SPAN_HZ + (double)best_g * FE_STEP_HZ)
              + d * FE_STEP_HZ;
    return FE_OK;
}

#endif /* FE_FIXED_POINT */
