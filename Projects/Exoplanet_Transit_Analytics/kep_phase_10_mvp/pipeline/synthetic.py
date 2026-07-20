"""
Synthetic light curve generators.

Two ground-truth demo targets — a Sun-like G star and a smaller,
cooler K dwarf — so the whole pipeline, the star rendering, AND the
dashboard's compare mode all work offline. Known truth doubles as the
validation harness: if the pipeline can't recover THESE parameters,
it can't be trusted on real data.
"""

import numpy as np
import lightkurve as lk

DEMO_TARGETS = {
    "SYNTH-DEMO": dict(
        period_days=3.5, t0=1.2, duration_days=0.15, depth=0.009,
        teff=5778.0, stellar_radius=1.0, seed=42,
    ),
    "SYNTH-DEMO-B": dict(
        period_days=5.2, t0=2.4, duration_days=0.19, depth=0.016,
        teff=4300.0, stellar_radius=0.68, seed=7,
    ),
    # Hot variable star for the Phase 7 variability mode: no transits,
    # a coherent 2% pulsation instead. Teff renders it blue-white.
    "SYNTH-VAR": dict(
        kind="sine", period_days=0.85, amplitude=0.02,
        teff=30000.0, stellar_radius=5.0, seed=11,
    ),
    # Wolf-Rayet-like star for the Phase 7-full SHO-PINN: quasi-periodic
    # wind modulation whose phase and amplitude wander (stochastic
    # clumping), so it is INCOHERENT — the SHO-PINN should recover a
    # period but a LOW quality factor, the opposite of SYNTH-VAR.
    "SYNTH-WR": dict(
        kind="wr", period_days=1.3, amplitude=0.03,
        teff=45000.0, stellar_radius=8.0, seed=23,
    ),
}

# Backward-compatible alias: the primary demo target's ground truth.
TRUTH = DEMO_TARGETS["SYNTH-DEMO"]


def make_synthetic_light_curve(
    params=None,
    n_days: float = 30.0,
    cadence_days: float = 0.0204,   # Kepler long cadence (29.4 min)
    noise_sigma: float = 2e-4,
):
    """
    Build a fake Kepler-like light curve:
      flat baseline + slow instrument drift + box transits + noise.

    Returns a lightkurve.LightCurve (same type the real pipeline uses).
    """
    p = params or TRUTH
    rng = np.random.default_rng(p.get("seed", 42))
    time = np.arange(0.0, n_days, cadence_days)

    # 1. Baseline
    flux = np.ones_like(time)

    # 2. Slow instrument drift (what Phase 2 flatten must remove)
    flux += 0.004 * np.sin(2 * np.pi * time / 18.0)
    flux += 0.002 * (time / n_days)

    # 3. The astrophysical signal
    if p.get("kind") == "sine":
        # Coherent pulsation (variability-mode demo). No drift term is
        # injected for this target: variability mode skips flattening,
        # so drift would contaminate the amplitude measurement.
        flux = np.ones_like(time)
        flux += p["amplitude"] * np.sin(2 * np.pi * time / p["period_days"])
    elif p.get("kind") == "wr":
        # Wolf-Rayet-like INCOHERENT variability: a quasi-period whose
        # phase random-walks and whose amplitude is modulated by smoothed
        # red noise. Lomb-Scargle still finds ~the period, but the signal
        # decoheres over time -> a low quality factor.
        flux = np.ones_like(time)
        phase_walk = np.cumsum(rng.normal(0.0, 0.18, size=time.shape))
        red = np.convolve(rng.normal(0.0, 1.0, size=time.shape),
                          np.ones(60) / 60, mode="same")
        amp_mod = 1.0 + 0.6 * red
        flux += (p["amplitude"] * amp_mod
                 * np.sin(2 * np.pi * time / p["period_days"] + phase_walk))
    else:
        # Box transits (what Phase 2 flatten must PRESERVE)
        phase = (time - p["t0"]) % p["period_days"]
        half = p["duration_days"] / 2
        in_transit = (phase < half) | (phase > p["period_days"] - half)
        flux[in_transit] -= p["depth"]

    # 4. Photon noise
    flux += rng.normal(0.0, noise_sigma, size=time.shape)

    return lk.LightCurve(time=time, flux=flux)
