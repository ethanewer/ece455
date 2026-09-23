/*
 * fft_est.c -- Goertzel peak estimator (candidate estimator variant).
 *
 * Magnitude peak of a length-n DFT over [f_lo, f_hi], then the same
 * log-parabolic refine as the zoom seed. Bin spacing is fs/n. An endpoint
 * peak stays unrefined and still returns FE_OK, because the crossing
 * estimator uses this frequency only as a cycle-slip reference.
 *
 * The scan is a Goertzel recurrence. It does not store a zero-padded
 * transform, so this file links into the same SRAM budget as the baseline.
 * It is float-only: a comparison path, not the shipped estimator.
 */
#include "freq_est.h"

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

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
    (void)t0;
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    double mean = 0.0;
    for (int i = 0; i < n; i++) {
        mean += (double)v[i];
    }
    mean /= (double)n;

    double df = fs / (double)n;
    int k_lo = (int)ceil(f_lo / df);
    int k_hi = (int)floor(f_hi / df);
    if (k_hi > n / 2) {
        k_hi = n / 2;
    }
    if (k_lo < 1 || k_hi <= k_lo + 1) {
        return FE_ERR_SEED;
    }

    double best = -1.0;
    int best_k = k_lo;
    for (int k = k_lo; k <= k_hi; k++) {
        double c1 = 2.0 * cos(2.0 * M_PI * (double)k / (double)n);
        double s1 = 0.0, s2 = 0.0;
        for (int i = 0; i < n; i++) {
            double s0 = ((double)v[i] - mean) + c1 * s1 - s2;
            s2 = s1;
            s1 = s0;
        }
        double p = s1 * s1 + s2 * s2 - c1 * s1 * s2;
        if (p > best) {
            best = p;
            best_k = k;
        }
    }
    if (best_k == k_lo || best_k == k_hi) {
        *out_hz = (double)best_k * df;
        return FE_OK;
    }
    double s3[3];
    for (int q = 0; q < 3; q++) {
        int k = best_k + q - 1;
        double c1 = 2.0 * cos(2.0 * M_PI * (double)k / (double)n);
        double s1 = 0.0, s2 = 0.0;
        for (int i = 0; i < n; i++) {
            double s0 = ((double)v[i] - mean) + c1 * s1 - s2;
            s2 = s1;
            s1 = s0;
        }
        s3[q] = s1 * s1 + s2 * s2 - c1 * s1 * s2;
    }
    *out_hz = (double)best_k * df + fe_log_parabolic3(s3, 1) * df;
    return FE_OK;
}
