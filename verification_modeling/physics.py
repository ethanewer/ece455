"""Synthetic FID generation and front-end noise model.

Physics: after the polarization pulse switches off, protons precess about
Earth's field B and induce a decaying sinusoid (the free induction decay)
in the pickup coil:

    v(t) = V0 * exp(-t/tau) * sin(2*pi*f_L*t + phi),   f_L = gamma'_p * B

Constant provenance (fixed per audit v0.0 -- both reviews flagged it):

* A water-sample PPM measures the DIAMAGNETICALLY SHIELDED proton in H2O:
  gamma'_p/2pi = 42.57638474 MHz/T (CODATA 2018; IAGA geomagnetic standard
  0.0425764 Hz/nT). The often-quoted 42.577478 MHz/T is the BARE proton and
  is 25.7 ppm higher -- a ~1.3 nT scale bias at 50 uT if used for absolute
  field values. We use the shielded value.
* Unit chain: 42.57638474 MHz/T = 42.57638474 Hz/uT = 0.0425764 Hz/nT.
  (An earlier revision wrote "42.577478 Hz/nT" and "gamma'_p = 42.5764
  Hz/nT" in comments -- both off by 1000x; the code constant was always
  0.0425764 Hz/nT.)
* Absolute-vs-anomaly decision (recorded for the objective function): a
  constant scale error (wrong gamma, or clock ppm) subtracts out of
  along-track ANOMALY contrast, which is the towfish mission. It does NOT
  subtract out of absolute field intensity. sigma_B below is therefore a
  per-cycle precision; absolute accuracy additionally carries the 25.7-ppm
  class scale terms, which are handled as reported biases, not noise.

gamma'_p = 0.0425764 Hz/nT (= 42.5764 MHz/T).  Target sensitivity < 1 nT
=> frequency precision < 0.0426 Hz per cycle.

This module is the "transducer" layer of the scoring harness: given coil +
front-end parameters it produces sampled, quantized records exactly as an
MCU would see them, so estimator code can be scored without hardware.
"""
import numpy as np

# Shielded proton in water, CODATA 2018 (42.57638474 MHz/T; the 2014 value
# 42.57638507 differs by 7.8 ppb). NOT the bare-proton value.
GAMMA_HZ_PER_T = 42.57638474e6
GAMMA_HZ_PER_NT = GAMMA_HZ_PER_T * 1e-9     # 0.0425764 Hz/nT
NT_PER_HZ = 1.0 / GAMMA_HZ_PER_NT           # 23.4872 nT per Hz

K_B = 1.380649e-23
T_AMBIENT = 300.0                           # K

# Active analog passband used for source-referred noise integration. The
# estimator may use a wider search interval for out-of-band stress tests.
NOISE_BAND = (1500.0, 2500.0)               # Hz

# Curie-law constants for the FID-amplitude estimate.
PROTON_DENSITY_WATER = 6.7e28               # protons / m^3
MU_PROTON = 1.4106e-26                      # proton magnetic moment [J/T]
MU_0 = 1.25663706e-6                        # H/m

try:                                        # numpy >= 2.0 renamed trapz
    _trapz = np.trapezoid
except AttributeError:                      # pragma: no cover
    _trapz = np.trapz


def larmor_hz(b_tesla: float) -> float:
    return GAMMA_HZ_PER_T * b_tesla


def estimate_v0(b_pol=0.02, n_turns=530, coil_radius_m=0.015,
                fill_factor=1.0, b_earth=50e-6) -> float:
    """Physics-based FID amplitude prediction [V, peak at t=0].

    Spin-1/2 Curie (Brillouin) law for the proton magnetization polarized by
    B_pol. For a nucleus of spin I and tabulated moment mu = gamma*hbar*I the
    static magnetization is (Abragam, "Principles of Nuclear Magnetism"):

        M0 = n * (gamma*hbar)^2 * I(I+1) * B_pol / (3 kT)
           = n * mu^2 * (I+1)/I * B_pol / (3 kT)

    For protons I = 1/2 this is M0 = n * mu_p^2 * B_pol / (k T) -- exactly
    THREE times the classical Langevin factor n*mu^2*B/(3kT) an earlier
    revision coded (audit E6: the classical 1/3 assumes the moment vector
    orients freely; a spin-1/2 moment does not). Cross-check: this formula
    gives the proton paramagnetic susceptibility of water
    chi = mu0 * M0/B = mu0 * n * mu_p^2 / (kT) ~ 4.1e-9 (SI) at 298 K, the
    literature value.

    The transverse magnetization M0 precesses at f_L (set by the EARTH field);
    Faraday's law through an N-turn coil of area A gives the initial peak EMF
        V0 = mu0 * M0 * (fill * pi r^2) * (2 pi f_L) * N

    Assumptions (documented, not hidden): uniform sample filling the coil,
    coil axis along B_pol so the precessing component is fully linked, and
    no loading/Q effects at t=0. This is an ORDER-OF-MAGNITUDE transducer
    model, deliberately exposed so bench captures can replace it. Headline results
    must state which V0 they assume. Defaults model a Hook-Line-class coil
    (530 turns, 3 cm bore) polarized at 20 mT.
    """
    m0 = (PROTON_DENSITY_WATER * MU_PROTON**2 * b_pol
          / (K_B * T_AMBIENT))                 # spin-1/2: /kT, NOT /3kT
    area = fill_factor * np.pi * coil_radius_m**2
    return float(MU_0 * m0 * area * 2.0 * np.pi * larmor_hz(b_earth) * n_turns)


def coil_thermal_noise_density(r_coil: float) -> float:
    """Johnson-Nyquist voltage noise density of the coil, V/sqrt(Hz)."""
    return float(np.sqrt(4.0 * K_B * T_AMBIENT * r_coil))


def input_noise_density(f: np.ndarray, r_coil: float, l_coil: float,
                        e_amp: float, i_amp: float) -> np.ndarray:
    """Total input-referred voltage noise density of coil + in-amp, V/sqrt(Hz).

    e_amp  : amplifier input voltage noise density [V/sqrt(Hz)]
    i_amp  : amplifier input current noise density [A/sqrt(Hz)]
    The current noise flows through the complex coil impedance Z(f) = R + jwL.
    """
    w = 2.0 * np.pi * f
    z_src = r_coil + 1j * w * l_coil
    e_coil = coil_thermal_noise_density(r_coil)
    return np.sqrt(e_coil**2 + e_amp**2 + (i_amp * np.abs(z_src))**2)


def front_end_noise_density(f, r_coil=14.0, l_coil=22e-3,
                            r_series=1.0e3, r_bias=100.0e3, c_couple=3.3e-9,
                            e_amp=5.5e-9, i_amp=1.5e-15) -> np.ndarray:
    """Coil-EMF-referred density of the active input network, V/sqrt(Hz).

    r_series and r_bias are the receiver's R1 and R2. c_couple is C5.
    e_amp defaults to the OPA4197 density specified below (V+)-3 V.
    The op-amp voltage noise is referred through the passive divider; the
    current noise flows through the series impedance. This is the input
    network only, not the later bandpass gain.
    """
    f = np.asarray(f, dtype=float)
    w = 2.0 * np.pi * f
    z_series = (r_coil + 1j * w * l_coil + 1.0 / (1j * w * c_couple)
                + r_series)
    gain = r_bias / (z_series + r_bias)
    e_coil = np.sqrt(4.0 * K_B * T_AMBIENT * r_coil)
    e_series = np.sqrt(4.0 * K_B * T_AMBIENT * r_series)
    e_bias = np.sqrt(4.0 * K_B * T_AMBIENT * r_bias)
    total = (e_coil**2 + e_series**2
             + (e_bias * np.abs(z_series / r_bias))**2
             + (e_amp / np.abs(gain))**2
             + (i_amp * np.abs(z_series))**2)
    return np.sqrt(total)


def input_noise_rms(r_coil=14.0, l_coil=22e-3, e_amp=1.4e-9, i_amp=0.1e-12,
                    f_lo=None, f_hi=None) -> float:
    """Coil-plus-amplifier RMS noise over a rectangular band [V].

    This omits R1, R2, and C5. Use front_end_noise_density for that input
    network, and the SPICE .noise analysis for the full receiver.
    """
    if f_lo is None:
        f_lo = NOISE_BAND[0]
    if f_hi is None:
        f_hi = NOISE_BAND[1]
    f = np.linspace(f_lo, f_hi, 2048)
    en = input_noise_density(f, r_coil, l_coil, e_amp, i_amp)
    return float(np.sqrt(_trapz(en**2, f)))


def _bandlimited_noise(n, fs, f_lo, f_hi, sigma, rng):
    """White Gaussian noise restricted to [f_lo, f_hi], RMS = sigma."""
    spec = np.fft.rfft(rng.normal(0.0, 1.0, size=n))
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    spec[(freqs < f_lo) | (freqs > f_hi)] = 0.0
    out = np.fft.irfft(spec, n)
    rms = float(np.sqrt(np.mean(out**2)))
    return out * (sigma / rms) if rms > 0 else out


def generate_record(b_tesla=50e-6, v0=2e-6, tau=1.5, phase=0.0,
                    fs=20_000.0, blanking_s=0.2, record_s=1.5,
                    r_coil=14.0, l_coil=22e-3, e_amp=1.4e-9, i_amp=0.1e-12,
                    f_lo=None, f_hi=None, gain=5000.0,
                    adc_bits=16, adc_fs=2.048, rng=None,
                    sigma_in=None, interferers=None,
                    comparator_walk_vn=None, rail_ripple=None) -> dict:
    """Simulate one measurement cycle end-to-end.

    v0 and b_tesla are deliberately INDEPENDENT knobs: the transducer chain
    (B_pol -> magnetization -> EMF) is modeled separately in estimate_v0.
    Callers that want physical consistency should derive v0 with that function rather than sweeping
    b_tesla at a fixed v0 (FID amplitude in reality scales as
    B_earth * B_pol through the precession frequency and Curie law).

    sigma_in overrides the analytic input-referred RMS noise (e.g. with a
    value extracted from a SPICE .noise run, as circuit_spec.py does).
    interferers: optional list of (freq_hz, peak_v_at_input) narrowband
    tones added to the INPUT (before gain) with ABSOLUTE amplitude in volts
    -- 60 Hz mains and harmonics are the scored systematics (the 30th
    harmonic of 60 Hz, 1.8 kHz, sits inside the FID band).

    comparator_walk_vn: rms noise at a comparator input [V]. Models the
    comparator time-walk systematic (B2): a zero-crossing front end
    timestamps each crossing with an error delta_t(t) = V_n / (dv/dt) =
    V_n / (2 pi f_L A(t)), which GROWS as the FID decays (MCU research doc:
    "zero-crossing shift ~ V_noise/(2 pi f A), growing as the FID decays").
    The recorded waveform carries the induced phase/frequency distortion
    sin(2 pi f (t - delta_t(t))), so any estimator downstream is scored
    with the real systematic, not just its variance.

    rail_ripple: optional (freq_hz, rail_ripple_v, psrr_db) tuple (B3).
    Supply ripple at freq_hz with rail amplitude rail_ripple_v couples into
    the signal path through the amplifier's power-supply rejection at that
    frequency: input-referred tone amplitude = rail_ripple_v * 10^(-psrr/20).
    Rail ripple inside the FID band killed two prior capstone teams; this
    makes it a scored interferer instead of a hand-wave.

    Returns dict with 't' (time since FID start), 'v_adc' (quantized samples
    at the ADC after front-end gain), and the true larmor frequency.
    """
    rng = np.random.default_rng(rng)
    if f_lo is None:
        f_lo = NOISE_BAND[0]
    if f_hi is None:
        f_hi = NOISE_BAND[1]
    f_l = larmor_hz(b_tesla)

    # Sample window: dead time (blanking) then record_s of usable FID.
    n = int(round(record_s * fs))
    t = blanking_s + np.arange(n) / fs

    if comparator_walk_vn:
        # B2: crossing-time shift delta_t(t) = V_n / (2 pi f A(t)); the
        # recorded waveform carries the time-varying delay. This is the
        # deterministic systematic of a comparator front end.
        dt_walk = comparator_walk_vn / (2.0 * np.pi * f_l * v0) * np.exp(t / tau)
        signal = v0 * np.exp(-t / tau) \
            * np.sin(2.0 * np.pi * f_l * (t - dt_walk) + phase)
    else:
        signal = v0 * np.exp(-t / tau) * np.sin(2.0 * np.pi * f_l * t + phase)
    for f_int, a_int in (interferers or []):
        signal = signal + a_int * np.sin(2.0 * np.pi * f_int * t)
    if rail_ripple is not None:
        f_r, v_rail, psrr_db = rail_ripple
        a_r = v_rail * 10.0 ** (-psrr_db / 20.0)   # input-referred
        signal = signal + a_r * np.sin(2.0 * np.pi * f_r * t)

    # Front-end noise: band-limited white (input-referred), i.e. what the
    # AFE bandpass leaves: white noise restricted to [f_lo, f_hi], RMS sigma_in.
    if sigma_in is None:
        sigma_in = input_noise_rms(r_coil, l_coil, e_amp, i_amp, f_lo, f_hi)
    noise = _bandlimited_noise(n, fs, f_lo, f_hi, sigma_in, rng)

    # Gain + ADC input range + quantization. A real converter clips at its
    # rails; modeling that here (not only as a score gate) is what lets
    # gain-staged candidates fail on clipping *in the record* (B6), the way
    # they would in hardware.
    v_amp = (signal + noise) * gain
    v_rail = adc_fs / 2.0
    n_clipped = int(np.count_nonzero(np.abs(v_amp) > v_rail))
    v_amp = np.clip(v_amp, -v_rail, v_rail)
    lsb = adc_fs / (2 ** adc_bits)
    v_adc = np.round(v_amp / lsb) * lsb

    return {"t": t, "v": v_amp, "v_adc": v_adc, "f_larmor": f_l,
            "sigma_in": sigma_in, "lsb": lsb, "fs": fs,
            "blanking_s": blanking_s, "record_s": record_s, "tau": tau,
            "n_clipped": n_clipped}


# Record synthesis from a measured or simulated front-end impulse response and
# input-referred noise spectrum. generate_record() above provides simpler unit
# vectors for estimator tests.
def _fftconvolve(a: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Full linear convolution via rfft (numpy-only fftconvolve)."""
    n = len(a) + len(h) - 1
    L = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, L) * np.fft.rfft(h, L), L)[:n]


def synthesize_adc_record(v0: float, f_l: float, tau: float,
                          h_t: np.ndarray, e_bins: np.ndarray,
                          sigma_in: float, phase: float,
                          noise_w: np.ndarray, blank_s: float,
                          fs: float = 20_000.0,
                          adc_bits: int = 16, adc_fs: float = 2.048,
                          ripple=None):
    """One E2E record from the candidate's SPICE characterization.

    v0, f_l, tau : FID physics (Curie-law amplitude, Larmor frequency, T2*)
    h_t          : the candidate's causal impulse response (SPICE .tran
                   ground truth), sampled at fs from t=0 for
                   blank_s + record_s
    e_bins       : the candidate's EMF-referred noise spectrum interpolated
                   onto the rfft bins of len(h_t)
    sigma_in     : full-sweep noise RMS the spectrum integrates to [V]
    phase        : FID phase for this MC record
    noise_w      : len(h_t) white unit-variance samples (the MC noise draw)
    blank_s      : effective blanking [s] (record starts at blank_s)
    ripple       : optional (freq_hz, input_referred_amp_v) rail-ripple
                   tone added to the EMF before the circuit response

    Returns (v_adc, n_clipped, peak_abs): the quantized ADC record, the
    clipped-sample count, and the peak |v_adc| for the clipping gate.

    The signal starts at t=0 (INSIDE the blanking window) and passes
    through the causal netlist response BEFORE the record window is
    sliced: multiplying a record that starts at blank_s by |H| alone
    rings the resonator at the record-start discontinuity and produced a
    spurious ~-3 mHz "tank pull" (audit E6 round 2).
    """
    n_full = len(h_t)
    n_blank = int(round(blank_s * fs))
    t_full = np.arange(n_full) / fs
    sig = v0 * np.exp(-t_full / tau) * np.sin(2.0 * np.pi * f_l * t_full
                                              + phase)
    if ripple is not None:
        f_r, a_r = ripple
        sig = sig + a_r * np.sin(2.0 * np.pi * f_r * t_full)
    sig_adc = _fftconvolve(sig, h_t)[:n_full]
    # EMF-referred noise shaped by the candidate's SPICE spectrum, then
    # through H once more (e_in x H = onoise at the ADC node).
    noise_emf = np.fft.irfft(np.fft.rfft(noise_w) * e_bins, n_full)
    rms = float(np.sqrt(np.mean(noise_emf**2)))
    if rms > 0:
        noise_emf *= sigma_in / rms
    noise_adc = _fftconvolve(noise_emf, h_t)[:n_full]
    v = sig_adc[n_blank:] + noise_adc[n_blank:]
    # ADC rails before quantization: gain-cranked candidates distort, not
    # wrap (B6); the clip count feeds the no_clipping gate.
    v_rail = adc_fs / 2.0
    n_clip = int(np.count_nonzero(np.abs(v) > v_rail))
    lsb = adc_fs / (2 ** adc_bits)
    v_adc = np.round(np.clip(v, -v_rail, v_rail) / lsb) * lsb
    return v_adc, n_clip, float(np.max(np.abs(v_adc)))
