/*
 * zc_est.c -- zero-crossing estimator (candidate estimator variant).
 *
 * The best-practice version of what the prior capstone teams built:
 * linearly-interpolated rising-edge crossing times, then a weighted mean
 * of adjacent periods with variance-optimal weights (the crossing-time
 * noise is sigma_v/|dv/dt|, so the weight is the smaller squared slope of
 * the pair -- this downweights the noisy late record where dv/dt
 * collapses). Periods implausible vs the coarse FFT peak are dropped
 * (cycle-slip robustness; a naive crossing-index regression fails
 * catastrophically on missed crossings).
 *
 * This estimator performs poorly at expected FID SNRs because crossing
 * timestamps discard inter-sample phase. It remains for controlled comparison
 * with the zoom estimator.
 */
#include "freq_est.h"

#include <math.h>

static float zc_x[FE_MAX_N];
static double zc_tc[FE_MAX_N / 2];          /* crossing times [s] */
static double zc_dv[FE_MAX_N / 2];          /* crossing slopes [V/sample] */

int zc_est_f32(const float *v, int n, double fs, double t0,
               double f_lo, double f_hi, double *out_hz)
{
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    (void)t0;                    /* uniform estimator calling convention */

    /* mean removal */
    double mean = 0.0;
    for (int i = 0; i < n; i++) {
        mean += (double)v[i];
    }
    mean /= (double)n;
    for (int i = 0; i < n; i++) {
        zc_x[i] = (float)((double)v[i] - mean);
    }

    /* linearly interpolated rising-edge crossings */
    int nc = 0;
    for (int i = 0; i + 1 < n; i++) {
        if (zc_x[i] < 0.0f && zc_x[i + 1] >= 0.0f) {
            double dv = (double)zc_x[i + 1] - (double)zc_x[i];
            if (dv == 0.0) {
                dv = 1e-12;
            }
            zc_tc[nc] = ((double)i - (double)zc_x[i] / dv) / fs;
            zc_dv[nc] = dv;
            nc++;
        }
    }
    if (nc < 9) {                           /* need >= 8 crossings */
        return FE_ERR_SEED;
    }

    /* cycle-slip reference: the coarse FFT peak */
    double f0;
    int rc = fft_est_f32(v, n, fs, t0, f_lo, f_hi, &f0);
    if (rc != FE_OK) {
        return rc;
    }
    double p0 = 1.0 / f0;

    double wsum = 0.0, psum = 0.0;
    int ng = 0;
    for (int i = 0; i + 1 < nc; i++) {
        double p = zc_tc[i + 1] - zc_tc[i];
        if (p > 0.5 * p0 && p < 1.5 * p0) {
            double w = zc_dv[i] < zc_dv[i + 1] ? zc_dv[i] : zc_dv[i + 1];
            w *= w;
            psum += w * p;
            wsum += w;
            ng++;
        }
    }
    if (ng < 4 || wsum <= 0.0 || psum <= 0.0) {
        return FE_ERR_SEED;
    }
    *out_hz = wsum / psum;
    return FE_OK;
}
