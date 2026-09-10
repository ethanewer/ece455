"""Synthetic FID generation and front-end noise model.

Physics: after the polarization pulse switches off, protons precess about
Earth's field B and induce a decaying sinusoid (the free induction decay)
in the pickup coil:

    v(t) = V0 * exp(-t/tau) * sin(2*pi*f_L*t + phi),   f_L = gamma'_p * B

Constant provenance (fixed per audit v0.0 -- both reviews flagged it):

* A water-sample PPM measures the DIAMAGNETICALLY SHIELDED proton in H2O:
  gamma'_p/2pi = 42.57638507 MHz/T (CODATA; IAGA geomagnetic standard
  0.0425764 Hz/nT). The often-quoted 42.577478 MHz/T is the BARE proton and
  is 25.7 ppm higher -- a ~1.3 nT scale bias at 50 uT if used for absolute
  field values. We use the shielded value.
* Unit chain: 42.57638507 MHz/T = 42.57638507 Hz/uT = 0.0425764 Hz/nT.
  (An earlier revision wrote "42.577478 Hz/nT" in a comment -- off by 1000x;
  the code constant was always correct.)
* Absolute-vs-anomaly decision (recorded for the objective function): a
  constant scale error (wrong gamma, or clock ppm) subtracts out of
  along-track ANOMALY contrast, which is the towfish mission. It does NOT
  subtract out of absolute field intensity. sigma_B below is therefore a
  per-cycle precision; absolute accuracy additionally carries the 25.7-ppm
  class scale terms, which are handled as reported biases, not noise.

gamma'_p = 42.5764 Hz/nT.  Target sensitivity < 1 nT  =>  frequency
precision < 0.0426 Hz per cycle.

This module is the "transducer" layer of the scoring harness: given coil +
front-end parameters it produces sampled, quantized records exactly as an
MCU would see them, so estimator code can be scored without hardware.
"""
import numpy as np

# Shielded proton in water, 25 C (CODATA 2018). NOT the bare-proton value.
GAMMA_HZ_PER_T = 42.57638507e6
GAMMA_HZ_PER_NT = GAMMA_HZ_PER_T * 1e-9     # 0.0425764 Hz/nT
NT_PER_HZ = 1.0 / GAMMA_HZ_PER_NT           # 23.4872 nT per Hz

K_B = 1.380649e-23
T_AMBIENT = 300.0                           # K

# Single source of truth for the front-end band (audits: the analytic noise
# integration and the SPICE .noise sweep must agree by construction).
NOISE_BAND = (500.0, 3500.0)                # Hz

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

    Curie law for the proton magnetization polarized by B_pol:
        M0 = n mu_p^2 B_pol / (3 kT)          [A/m]   (n = proton density)
    The transverse magnetization M0 precesses at f_L (set by the EARTH field);
    Faraday's law through an N-turn coil of area A gives the initial peak EMF
        V0 = mu0 * M0 * (fill * pi r^2) * (2 pi f_L) * N

    Assumptions (documented, not hidden): uniform sample filling the coil,
    coil axis along B_pol so the precessing component is fully linked, and
    no loading/Q effects at t=0. This is an ORDER-OF-MAGNITUDE transducer
    model, deliberately exposed so the optimizer (and the bench capture)
    can be scored against it: the audits' point is that headline results
    must state which V0 they assume. Defaults model a Hook-Line-class coil
    (530 turns, 3 cm bore) polarized at 20 mT.
    """
    m0 = PROTON_DENSITY_WATER * MU_PROTON**2 * b_pol / (3.0 * K_B * T_AMBIENT)
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


def input_noise_rms(r_coil=120.0, l_coil=2e-3, e_amp=7e-9, i_amp=0.05e-12,
                    f_lo=None, f_hi=None) -> float:
    """Input-referred RMS noise in the FID band [V]. Defaults to NOISE_BAND."""
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
                    r_coil=120.0, l_coil=2e-3, e_amp=7e-9, i_amp=0.05e-12,
                    f_lo=None, f_hi=None, gain=5000.0,
                    adc_bits=16, adc_fs=2.048, rng=None,
                    sigma_in=None, interferers=None) -> dict:
    """Simulate one measurement cycle end-to-end.

    v0 and b_tesla are deliberately INDEPENDENT knobs: the transducer chain
    (B_pol -> magnetization -> EMF) is modeled separately in estimate_v0,
    and both circuit_spec.py and the run_scoring.py grid set v0 from it.
    Callers that want physical consistency should do the same rather than
    sweeping b_tesla at a fixed v0 (FID amplitude in reality scales as
    B_earth * B_pol through the precession frequency and Curie law).

    sigma_in overrides the analytic input-referred RMS noise (e.g. with a
    value extracted from a SPICE .noise run, as circuit_spec.py does).
    interferers: optional list of (freq_hz, peak_v_at_input) narrowband
    tones added to the INPUT (before gain) with ABSOLUTE amplitude in volts
    -- 60 Hz mains and harmonics are the scored systematics (the 30th
    harmonic of 60 Hz, 1.8 kHz, sits inside the FID band).

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

    signal = v0 * np.exp(-t / tau) * np.sin(2.0 * np.pi * f_l * t + phase)
    for f_int, a_int in (interferers or []):
        signal = signal + a_int * np.sin(2.0 * np.pi * f_int * t)

    # Front-end noise: band-limited white (input-referred), i.e. what the
    # AFE bandpass leaves: white noise restricted to [f_lo, f_hi], RMS sigma_in.
    if sigma_in is None:
        sigma_in = input_noise_rms(r_coil, l_coil, e_amp, i_amp, f_lo, f_hi)
    noise = _bandlimited_noise(n, fs, f_lo, f_hi, sigma_in, rng)

    # Gain + ADC quantization.
    v_amp = (signal + noise) * gain
    lsb = adc_fs / (2 ** adc_bits)
    v_adc = np.round(v_amp / lsb) * lsb

    return {"t": t, "v": v_amp, "v_adc": v_adc, "f_larmor": f_l,
            "sigma_in": sigma_in, "lsb": lsb, "fs": fs,
            "blanking_s": blanking_s, "record_s": record_s, "tau": tau}
