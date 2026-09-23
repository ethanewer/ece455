/* Exercise the fixed-point estimator at FE_MAX_N under sanitizers. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "freq_est.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static int run_case(int n, double fs, double tau, double truth_hz)
{
    const double t0 = 0.2;
    int32_t *samples = malloc((size_t)n * sizeof(*samples));
    if (samples == NULL) {
        return 2;
    }
    for (int i = 0; i < n; i++) {
        double t = t0 + (double)i / fs;
        double signal = 0.2 * 2147483647.0 * exp(-t / tau)
                        * sin(2.0 * M_PI * truth_hz * t);
        samples[i] = (int32_t)signal;
    }
    double estimate_hz = 0.0;
    int rc = freq_est_fixed(samples, n, fs, t0, 500.0, 3500.0,
                            &estimate_hz);
    free(samples);
    if (rc != FE_OK || fabs(estimate_hz - truth_hz) > 0.0426) {
        fprintf(stderr,
                "fixed bounds test failed: n=%d rc=%d estimate=%.9f\n",
                n, rc, estimate_hz);
        return 1;
    }
    printf("fixed bounds sanitizer PASS n=%d: %.9f Hz\n", n, estimate_hz);
    return 0;
}

int main(void)
{
    const double fs = 30000.0;
    const double truth_hz = 2128.819237;
    /* Full 1.5 s record, and a shorter record whose block count used to
     * exceed the decay-fit buffer and silently force tau = 1 s. */
    int rc = run_case(FE_MAX_N, fs, 1.5, truth_hz);
    if (rc != 0) {
        return rc;
    }
    return run_case(20000, fs, 0.3, truth_hz);
}
