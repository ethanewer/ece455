"""Synthetic FID generation and front-end noise model.

Physics: after the polarization pulse switches off, protons precess about
Earth's field B and induce a decaying sinusoid (the free induction decay)
in the pickup coil:

    v(t) = V0 * exp(-t/tau) * sin(2*pi*f_L*t + phi),   f_L = gamma_p * B

gamma_p = 42.577478 MHz/T  =>  42.577478 Hz/nT.
Target sensitivity < 1 nT  =>  frequency precision < 0.0426 Hz.

This module is the "transducer" layer of the scoring harness: given coil +
front-end parameters it produces sampled, quantized records exactly as an
MCU would see them, so estimator code can be scored without hardware.
"""
import numpy as np

GAMMA_HZ_PER_T = 42.577478e6          # proton gyromagnetic ratio in water (Hz/T)
GAMMA_HZ_PER_NT = GAMMA_HZ_PER_T * 1e-9
K_B = 1.380649e-23
T_AMBIENT = 300.0                     # K


def larmor_hz(b_tesla: float) -> float:
    return GAMMA_HZ_PER_T * b_tesla


def coil_thermal_noise_density(r_coil: float) -> float:
    """Johnson-Nyquist voltage noise density of the coil, V/sqrt(Hz)."""
    return float(np.sqrt(4.0 * K_B * T_AMBIENT * r_coil))


def input_noise_density(f: np.ndarray, r_coil: float, l_coil: float,
                        e_amp: float, i_amp: float) -> np.ndarray:
    """Total input-referred voltage noise density of coil + in-amp, V/sqrt(Hz).

    e_amp  : amplifier input voltage noise density [V/sqrt(Hz)]
    i_amp  : amplifier input current noise density [A/sqrt(Hz)]
    The current noise flows through the complex coil impedance Z(f) = R + jwL.
    Coil thermal noise is white (R dominates for l_coil small vs R at 1-3 kHz
    when wL << R; kept general here).
    """
    w = 2.0 * np.pi * f
    z_src = r_coil + 1j * w * l_coil
    e_coil = coil_thermal_noise_density(r_coil)
    return np.sqrt(e_coil**2 + e_amp**2 + (i_amp * np.abs(z_src))**2)


def input_noise_rms(r_coil=120.0, l_coil=2e-3, e_amp=7e-9, i_amp=0.05e-12,
                    f_lo=700.0, f_hi=3500.0) -> float:
    """Input-referred RMS noise in the FID band [V]."""
    f = np.linspace(f_lo, f_hi, 2048)
    en = input_noise_density(f, r_coil, l_coil, e_amp, i_amp)
    return float(np.sqrt(np.trapz(en**2, f)))


def generate_record(b_tesla=50e-6, v0=2e-6, tau=1.5, phase=0.0,
                    fs=20_000.0, blanking_s=0.2, record_s=1.5,
                    r_coil=120.0, l_coil=2e-3, e_amp=7e-9, i_amp=0.05e-12,
                    f_lo=700.0, f_hi=3500.0, gain=5000.0,
                    adc_bits=16, adc_fs=2.048, rng=None,
                    sigma_in=None) -> dict:
    """Simulate one measurement cycle end-to-end.

    sigma_in overrides the analytic input-referred RMS noise (e.g. with a
    value extracted from a SPICE .noise run, as circuit_spec.py does).

    Returns dict with 't' (time since FID start), 'v_adc' (quantized samples
    at the ADC after front-end gain), and the true larmor frequency.
    """
    rng = np.random.default_rng(rng)
    f_l = larmor_hz(b_tesla)

    # Sample window: dead time (blanking) then record_s of usable FID.
    t0, t1 = blanking_s, blanking_s + record_s
    n = int(round(record_s * fs))
    t = t0 + np.arange(n) / fs

    signal = v0 * np.exp(-t / tau) * np.sin(2.0 * np.pi * f_l * t + phase)

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


def _bandlimited_noise(n, fs, f_lo, f_hi, sigma, rng):
    """White Gaussian noise restricted to [f_lo, f_hi], RMS = sigma."""
    spec = np.fft.rfft(rng.normal(0.0, 1.0, size=n))
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    spec[(freqs < f_lo) | (freqs > f_hi)] = 0.0
    out = np.fft.irfft(spec, n)
    rms = float(np.sqrt(np.mean(out**2)))
    return out * (sigma / rms) if rms > 0 else out
