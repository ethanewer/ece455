/*
 * zc_est.c -- zero-crossing estimator (candidate estimator variant).
 *
 * Linearly interpolated rising-edge crossings, then a weighted mean of
 * adjacent periods. Crossing-time noise is sigma_v/|dv/dt|, so the weight
 * is the smaller squared slope of the pair. Periods implausible against
 * the coarse spectral peak are dropped.
 *
 * Crossings are consumed as they are found. The record itself stays in the
 * caller's buffer.
 */
#include "freq_est.h"

#include <math.h>

int zc_est_f32(const float *v, int n, double fs, double t0,
               double f_lo, double f_hi, double *out_hz)
{
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    (void)t0;

    double mean = 0.0;
    for (int i = 0; i < n; i++) {
        mean += (double)v[i];
    }
    mean /= (double)n;

    double f0;
    int rc = fft_est_f32(v, n, fs, t0, f_lo, f_hi, &f0);
    if (rc != FE_OK) {
        return rc;
    }
    double p0 = 1.0 / f0;

    float prev = (float)((double)v[0] - mean);
    double prev_tc = 0.0, prev_dv = 0.0;
    int have_prev = 0;
    int nc = 0;
    double wsum = 0.0, psum = 0.0;
    int ng = 0;
    for (int i = 0; i + 1 < n; i++) {
        float cur = (float)((double)v[i + 1] - mean);
        if (prev < 0.0f && cur >= 0.0f) {
            double dv = (double)cur - (double)prev;
            if (dv == 0.0) {
                dv = 1e-12;
            }
            double tc = ((double)i - (double)prev / dv) / fs;
            if (have_prev) {
                double p = tc - prev_tc;
                if (p > 0.5 * p0 && p < 1.5 * p0) {
                    double w = prev_dv < dv ? prev_dv : dv;
                    w *= w;
                    psum += w * p;
                    wsum += w;
                    ng++;
                }
            }
            prev_tc = tc;
            prev_dv = dv;
            have_prev = 1;
            nc++;
        }
        prev = cur;
    }
    if (nc < 9 || ng < 4 || wsum <= 0.0 || psum <= 0.0) {
        return FE_ERR_SEED;
    }
    *out_hz = wsum / psum;
    return FE_OK;
}
