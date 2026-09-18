/* Exercise the fixed-point estimator at FE_MAX_N under sanitizers. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "freq_est.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

int main(void)
{
    const int n = FE_MAX_N;
    const double fs = 20000.0;
    const double t0 = 0.2;
    const double truth_hz = 2128.819237;
    int32_t *samples = malloc((size_t)n * sizeof(*samples));
    if (samples == NULL) {
        return 2;
    }

    for (int i = 0; i < n; i++) {
        double t = t0 + (double)i / fs;
        double signal = 0.2 * 2147483647.0 * exp(-t / 1.5)
                        * sin(2.0 * M_PI * truth_hz * t);
        samples[i] = (int32_t)signal;
    }

    double estimate_hz = 0.0;
    int rc = freq_est_fixed(samples, n, fs, t0, 500.0, 3500.0,
                            &estimate_hz);
    free(samples);

    if (rc != FE_OK || fabs(estimate_hz - truth_hz) > 0.0426) {
        fprintf(stderr, "fixed bounds test failed: rc=%d estimate=%.9f\n",
                rc, estimate_hz);
        return 1;
    }
    printf("fixed bounds sanitizer PASS: %.9f Hz\n", estimate_hz);
    return 0;
}
