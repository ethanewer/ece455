/*
 * fft_est.c -- zero-padded FFT peak estimator (candidate estimator variant).
 *
 * This implementation uses the magnitude peak of a zero-padded FFT with
 * log-parabolic interpolation. It is biased on damped sinusoids and limited
 * to roughly 1/T_record resolution. It remains for comparison with the zoom
 * estimator.
 *
 * The zero-padded FFT is computed by an in-place radix-2 transform (the
 * host scoring path runs records of 30000 samples -> L = 2^19); on-target
 * a streaming DFT/Goertzel pair would compute the same quantity. This
 * variant is float-only: it is an exploration candidate, not the shipped
 * baseline, so no Q31 port is provided.
 */
#include "freq_est.h"

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define FE_ZERO_PAD   16
#define FE_FFT_LOG    19                    /* 2^19 = 524288 >= 16*32768 */
#define FE_FFT_MAX    (1 << FE_FFT_LOG)

static double fe_fr[FE_FFT_MAX], fe_fi[FE_FFT_MAX];

/* In-place iterative radix-2 DIT FFT (sign convention e^{-j2pi kn/N}). */
static void fe_fft(double *re, double *im, int n)
{
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            double tr = re[i]; re[i] = re[j]; re[j] = tr;
            double ti = im[i]; im[i] = im[j]; im[j] = ti;
        }
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = -2.0 * M_PI / (double)len;
        double wr = cos(ang), wi = sin(ang);
        int half = len >> 1;
        for (int i = 0; i < n; i += len) {
            double cwr = 1.0, cwi = 0.0;
            for (int j = 0; j < half; j++) {
                int a = i + j, b = i + j + half;
                double xr = re[b] * cwr - im[b] * cwi;
                double xi = re[b] * cwi + im[b] * cwr;
                re[b] = re[a] - xr; im[b] = im[a] - xi;
                re[a] += xr; im[a] += xi;
                double nwr = cwr * wr - cwi * wi;
                cwi = cwr * wi + cwi * wr;
                cwr = nwr;
            }
        }
    }
}

static double fe_log_parabolic3(const double *s, int k)
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

int fft_est_f32(const float *v, int n, double fs, double t0,
                double f_lo, double f_hi, double *out_hz)
{
    (void)t0;                    /* uniform estimator calling convention */
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    int L = 1;
    while (L < FE_ZERO_PAD * n) {
        L <<= 1;
        if (L > FE_FFT_MAX) {
            return FE_ERR_INPUT;
        }
    }

    /* mean removal + zero padding */
    double mean = 0.0;
    for (int i = 0; i < n; i++) {
        mean += (double)v[i];
    }
    mean /= (double)n;
    for (int i = 0; i < n; i++) {
        fe_fr[i] = (double)v[i] - mean;
        fe_fi[i] = 0.0;
    }
    for (int i = n; i < L; i++) {
        fe_fr[i] = 0.0;
        fe_fi[i] = 0.0;
    }
    fe_fft(fe_fr, fe_fi, L);

    double df = fs / (double)L;
    int k_lo = (int)ceil(f_lo / df);
    int k_hi = (int)floor(f_hi / df);
    if (k_hi > L / 2) {
        k_hi = L / 2;
    }
    if (k_lo < 1 || k_hi <= k_lo + 1) {
        return FE_ERR_SEED;
    }
    double best = -1.0;
    int best_k = k_lo;
    for (int k = k_lo; k <= k_hi; k++) {
        double p = fe_fr[k] * fe_fr[k] + fe_fi[k] * fe_fi[k];
        if (p > best) {
            best = p;
            best_k = k;
        }
    }
    if (best_k == k_lo || best_k == k_hi) {
        *out_hz = (double)best_k * df;      /* can't refine at the edge */
        return FE_OK;
    }
    /* log-parabolic refine on |X|^2 (log of the power is a constant factor
     * of log of the magnitude; the parabola is identical). */
    double s3[3];
    for (int q = 0; q < 3; q++) {
        int k = best_k + q - 1;
        s3[q] = fe_fr[k] * fe_fr[k] + fe_fi[k] * fe_fi[k];
    }
    *out_hz = (double)best_k * df + fe_log_parabolic3(s3, 1) * df;
    return FE_OK;
}
