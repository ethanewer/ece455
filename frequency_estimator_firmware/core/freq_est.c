/*
 * freq_est.c -- portable FID frequency estimator core (C1).
 *
 * This is the production estimator implementation. A NumPy mirror in
 * frequency_estimator_firmware/host exists only for debugging. Host tests
 * cross-check both implementations on the same golden vectors.
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
 *      fit down to 0.5 of peak, clipped to [0.1, 20] s;
 *   6. weighted zoom: S(df) = |sum_k w_k z_b[k] e^{-j2 pi df t_b[k]}|^2
 *      with w = exp(-t_b/tau) over +/-FE_SPAN_HZ at FE_STEP_HZ;
 *      log-parabolic refine. An endpoint peak is FE_ERR_SEED.
 *
 * The full-rate record is consumed on the fly. Only the decimated envelope
 * is retained, which is what keeps a 1.5 s / 30 kSPS record inside the
 * RP2350 SRAM budget.
 *
 * Numeric modes (one compile switch; CI tests both on the same vectors):
 *   default          : float32 signal path (M33 / M4F / M7 class)
 *   -DFE_FIXED_POINT : Q31 signal path, int64 accumulators, table NCO
 */
#include "freq_est.h"

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define FE_NGRID   2001                       /* 2*20/0.02 + 1 */
#define FE_OUT_MAX (FE_MAX_N / FE_DEC)
/*
 * n_blk = m / floor(m/256) is at most 511 for every m >= 256. A smaller
 * buffer used to skip the decay fit on many legal lengths and silently
 * substitute tau = 1 s.
 */
#define FE_ENV_MAX 512

static double fir[FE_FIR_TAPS];

typedef double (*fe_sample_fn)(int index, void *ctx);

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

/* Coarse seed shared by the float and Q31 builds, including the
 * log-parabolic correction. sample(i) is the centered waveform. */
static int fe_coarse_seed(fe_sample_fn sample, void *ctx, int nseed,
                          double fs, double f_lo, double f_hi, double *f0_out)
{
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
            double s0 = sample(i, ctx) + c1 * s1 - s2;
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
        *f0_out = (double)best_k * df_bin;
        return FE_ERR_SEED;
    }
    double s3[3];
    for (int q = 0; q < 3; q++) {
        double f = (double)(best_k + q - 1) * df_bin;
        double sr = 0.0, si = 0.0;
        for (int i = 0; i < nseed; i++) {
            double ang = -2.0 * M_PI * f * (double)i / fs;
            double x = sample(i, ctx);
            sr += x * cos(ang);
            si += x * sin(ang);
        }
        s3[q] = sr * sr + si * si;
    }
    *f0_out = (double)best_k * df_bin + fe_log_parabolic(s3, 1) * df_bin;
    return FE_OK;
}

typedef double (*fe_mag_fn)(int index, void *ctx);

static double fe_tau(fe_mag_fn mag, void *ctx, int m, double dtb)
{
    static double env[FE_ENV_MAX];
    int blk = m / 256;
    int n_blk = blk > 0 ? m / blk : 0;
    if (n_blk < 8 || n_blk > FE_ENV_MAX) {
        return 1.0;
    }
    for (int b = 0; b < n_blk; b++) {
        double e = 0.0;
        int begin = b * blk;
        for (int j = 0; j < blk; j++) {
            double sample = mag(begin + j, ctx);
            if (sample > e) {
                e = sample;
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

/* ================================================================== */
/* float32 mode                                                        */
/* ================================================================== */
#ifndef FE_FIXED_POINT

struct fe_f32_ctx {
    const float *v;
    double mean;
};

static double fe_f32_at(int index, void *ctx)
{
    struct fe_f32_ctx *c = ctx;
    return (double)(float)((double)c->v[index] - c->mean);
}

struct fe_f32_env {
    const float *zre;
    const float *zim;
};

static double fe_f32_mag(int index, void *ctx)
{
    struct fe_f32_env *c = ctx;
    double zr = (double)c->zre[index];
    double zi = (double)c->zim[index];
    return sqrt(zr * zr + zi * zi);
}

void fe_zoom_point_f32(const float *zre, const float *zim, const float *w,
                       int m, double tb0, double dtb, double df,
                       double *s_out)
{
    /* Single-precision rotator and accumulator. The RP2350 FPU is
     * single precision; a double sum here is software-emulated. */
    float e_re = (float)cos(-2.0 * M_PI * df * tb0);
    float e_im = (float)sin(-2.0 * M_PI * df * tb0);
    float d_re = (float)cos(-2.0 * M_PI * df * dtb);
    float d_im = (float)sin(-2.0 * M_PI * df * dtb);
    float sr = 0.0f, si = 0.0f;
    for (int k = 0; k < m; k++) {
        float zr = zre[k], zi = zim[k], wk = w[k];
        sr += wk * (zr * e_re - zi * e_im);
        si += wk * (zr * e_im + zi * e_re);
        float n_re = e_re * d_re - e_im * d_im;
        e_im = e_re * d_im + e_im * d_re;
        e_re = n_re;
    }
    *s_out = (double)sr * (double)sr + (double)si * (double)si;
}

int freq_est_f32(const float *v, int n, double fs, double t0,
                 double f_lo, double f_hi, double *out_hz)
{
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    static float zbre[FE_OUT_MAX], zbim[FE_OUT_MAX], w[FE_OUT_MAX];
    static double sgrid[FE_NGRID];
    float zr_line[FE_FIR_TAPS], zi_line[FE_FIR_TAPS];

    double mean = 0.0;
    for (int i = 0; i < n; i++) {
        mean += (double)v[i];
    }
    mean /= (double)n;

    fe_fir_init(fs);
    struct fe_f32_ctx samples = {v, mean};
    int nseed = n < FE_SEED_WINDOW ? n : FE_SEED_WINDOW;
    double f0 = 0.0;
    int seed_rc = fe_coarse_seed(fe_f32_at, &samples, nseed, fs, f_lo, f_hi,
                                 &f0);
    if (seed_rc != FE_OK) {
        return seed_rc;
    }

    double e_re = cos(-2.0 * M_PI * f0 * t0);
    double e_im = sin(-2.0 * M_PI * f0 * t0);
    double d_re = cos(-2.0 * M_PI * f0 / fs);
    double d_im = sin(-2.0 * M_PI * f0 / fs);
    int filled = 0, base = 0, m = 0;
    for (int i = 0; i < n; i++) {
        float x = (float)((double)v[i] - mean);
        float zr = (float)((double)x * e_re);
        float zi = (float)((double)x * e_im);
        if (filled < FE_FIR_TAPS) {
            zr_line[filled] = zr;
            zi_line[filled] = zi;
            filled++;
        } else {
            zr_line[base] = zr;
            zi_line[base] = zi;
            base = (base + 1) % FE_FIR_TAPS;
        }
        double n_re = e_re * d_re - e_im * d_im;
        e_im = e_re * d_im + e_im * d_re;
        e_re = n_re;
        if (i < FE_FIR_TAPS - 1 ||
            ((i - (FE_FIR_TAPS - 1)) % FE_DEC) != 0) {
            continue;
        }
        if (m >= FE_OUT_MAX) {
            return FE_ERR_INPUT;
        }
        double sr = 0.0, si = 0.0;
        for (int j = 0; j < FE_FIR_TAPS; j++) {
            int idx = (base + j) % FE_FIR_TAPS;
            sr += fir[j] * (double)zr_line[idx];
            si += fir[j] * (double)zi_line[idx];
        }
        zbre[m] = (float)sr;
        zbim[m] = (float)si;
        m++;
    }
    double dtb = (double)FE_DEC / fs;

    struct fe_f32_env envelope = {zbre, zbim};
    double tau = fe_tau(fe_f32_mag, &envelope, m, dtb);

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
        return FE_ERR_SEED;
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

struct fe_q_ctx {
    const int32_t *v;
    int32_t mean;
};

static double fe_q_at(int index, void *ctx)
{
    struct fe_q_ctx *c = ctx;
    return (double)(c->v[index] - c->mean);
}

struct fe_q_env {
    const int32_t *zre;
    const int32_t *zim;
};

static double fe_q_mag(int index, void *ctx)
{
    struct fe_q_env *c = ctx;
    double zr = (double)c->zre[index];
    double zi = (double)c->zim[index];
    return sqrt(zr * zr + zi * zi);
}

int freq_est_fixed(const int32_t *v, int n, double fs, double t0,
                   double f_lo, double f_hi, double *out_hz)
{
    if (n < 512 || n > FE_MAX_N) {
        return FE_ERR_INPUT;
    }
    static int32_t zbre[FE_OUT_MAX], zbim[FE_OUT_MAX], w[FE_OUT_MAX];
    static int32_t fir_q[FE_FIR_TAPS];
    static double sgrid[FE_NGRID];
    int32_t zr_line[FE_FIR_TAPS], zi_line[FE_FIR_TAPS];

    int64_t mean_acc = 0;
    for (int i = 0; i < n; i++) {
        mean_acc += v[i];
    }
    int32_t mean32 = (int32_t)(mean_acc / n);

    fe_fir_init(fs);
    struct fe_q_ctx samples = {v, mean32};
    int nseed = n < FE_SEED_WINDOW ? n : FE_SEED_WINDOW;
    double f0 = 0.0;
    int seed_rc = fe_coarse_seed(fe_q_at, &samples, nseed, fs, f_lo, f_hi,
                                 &f0);
    if (seed_rc != FE_OK) {
        return seed_rc;
    }

    fe_nco_init();
    for (int j = 0; j < FE_FIR_TAPS; j++) {
        fir_q[j] = (int32_t)(fir[j] * 2147483647.0);
    }
    uint32_t ph = (uint32_t)((t0 * f0 - floor(t0 * f0)) * 4294967296.0);
    uint32_t dph = (uint32_t)(f0 / fs * FE_FRAC);
    int filled = 0, base = 0, m = 0;
    for (int i = 0; i < n; i++) {
        int32_t s, c;
        fe_nco_cossin(ph, &c, &s);
        int32_t x = v[i] - mean32;
        int32_t zr = (int32_t)(((int64_t)x * c) >> 31);
        int32_t zi = (int32_t)(-(((int64_t)x * s) >> 31));
        if (filled < FE_FIR_TAPS) {
            zr_line[filled] = zr;
            zi_line[filled] = zi;
            filled++;
        } else {
            zr_line[base] = zr;
            zi_line[base] = zi;
            base = (base + 1) % FE_FIR_TAPS;
        }
        ph += dph;
        if (i < FE_FIR_TAPS - 1 ||
            ((i - (FE_FIR_TAPS - 1)) % FE_DEC) != 0) {
            continue;
        }
        if (m >= FE_OUT_MAX) {
            return FE_ERR_INPUT;
        }
        int64_t sr = 0, si = 0;
        for (int j = 0; j < FE_FIR_TAPS; j++) {
            int idx = (base + j) % FE_FIR_TAPS;
            sr += (int64_t)fir_q[j] * zr_line[idx];
            si += (int64_t)fir_q[j] * zi_line[idx];
        }
        zbre[m] = (int32_t)(sr >> 31);
        zbim[m] = (int32_t)(si >> 31);
        m++;
    }

    struct fe_q_env envelope = {zbre, zbim};
    double tau = fe_tau(fe_q_mag, &envelope, m, (double)FE_DEC / fs);

    for (int k = 0; k < m; k++) {
        double wk = exp(-(t0 + (double)k * (double)FE_DEC / fs) / tau);
        w[k] = (int32_t)(wk * 2147483647.0);
    }
    int ng = 0, best_g = 0;
    for (int g = 0; g < FE_NGRID; g++) {
        double dfc = -FE_SPAN_HZ + (double)g * FE_STEP_HZ;
        uint32_t phg = (uint32_t)(int64_t)(t0 * dfc * FE_FRAC);
        uint32_t dphg = (uint32_t)(int64_t)
                        (dfc * (double)FE_DEC / fs * FE_FRAC);
        int64_t sr = 0, si = 0;
        for (int k = 0; k < m; k++) {
            int32_t s, c;
            fe_nco_cossin(phg, &c, &s);
            int64_t pr = ((int64_t)zbre[k] * w[k]) >> 31;
            int64_t pi = ((int64_t)zbim[k] * w[k]) >> 31;
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
        return FE_ERR_SEED;
    }
    double d = fe_log_parabolic(sgrid, best_g);
    *out_hz = f0 + (-FE_SPAN_HZ + (double)best_g * FE_STEP_HZ)
              + d * FE_STEP_HZ;
    return FE_OK;
}

#endif /* FE_FIXED_POINT */
