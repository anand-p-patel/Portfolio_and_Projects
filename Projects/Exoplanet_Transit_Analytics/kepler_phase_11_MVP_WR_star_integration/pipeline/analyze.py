"""
Phase 3 — Classical baseline analysis (Box Least Squares).

BLS is the standard transit-search algorithm the Kepler mission itself
used. It is deliberately the BASELINE here: when the PINN lands in
Phase 4, its Rp/R* predictions get validated against (a) these BLS
numbers and (b) the NASA confirmed-planet catalogue. A model without a
baseline is unfalsifiable.
"""

import numpy as np
import lightkurve as lk
from astropy.timeseries import BoxLeastSquares

# Physical transit durations to test (days), ~0.5 h to ~7 h. A small
# fixed set keeps the search bounded and mission-independent.
BLS_DURATIONS = np.array([0.02, 0.04, 0.06, 0.08, 0.10, 0.14, 0.18,
                          0.24, 0.30])


def run_bls(time, flux, min_period: float = 0.5, max_period: float = 15.0,
            n_periods: int = 5000):
    """
    Run a two-stage Box Least Squares period search on a flattened light
    curve.

    Uses astropy's BoxLeastSquares directly with explicit period and
    duration grids, rather than lightkurve's `to_periodogram`: the wrapper
    calls astropy's autoperiod internally even when handed a period grid,
    and that auto grid scales with the total time-span — for stitched,
    widely-separated TESS sectors it explodes past astropy's evaluation
    limit and raises.

    A single coarse grid, however, under-resolves the period on long
    baselines: a full Kepler mission is ~4 years, so a period off by one
    coarse step (~0.003 d) drifts by ~0.3 d over ~300 cycles and smears
    the folded transit, halving the apparent depth. So:

      Stage 1 — coarse grid over [min_period, max_period] finds the peak.
      Stage 2 — a fine local grid around that peak pins the period so
                every transit stacks coherently and the depth is true.

    Bounded (~25k evaluations total), fast, and cadence-agnostic.

    Returns
    -------
    dict with keys:
        period_days, t0, duration_days, depth, rp_over_rstar, method
    """
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    bls = BoxLeastSquares(time, flux)

    # Stage 1: coarse global search.
    coarse = np.linspace(min_period, max_period, n_periods)
    res = bls.power(coarse, BLS_DURATIONS)
    p0 = float(res.period[int(np.argmax(res.power))])

    # Stage 2: fine local refine. The true period is within ~1 coarse
    # step of the peak; bracket it generously and resolve finely.
    step = (max_period - min_period) / (n_periods - 1)
    lo = max(p0 - 5 * step, 1e-3)
    fine = np.linspace(lo, p0 + 5 * step, 20000)
    res = bls.power(fine, BLS_DURATIONS)

    best = int(np.argmax(res.power))
    depth = float(res.depth[best])
    # Physics: Delta F = (Rp / R*)^2  =>  Rp/R* = sqrt(Delta F)
    rp_over_rstar = float(np.sqrt(max(depth, 0.0)))

    return {
        "method": "bls",
        "period_days": float(res.period[best]),
        "t0": float(res.transit_time[best]),
        "duration_days": float(res.duration[best]),
        "depth": depth,
        "rp_over_rstar": rp_over_rstar,
    }


def run_variability(time, flux, min_period=None, max_period=None):
    """
    Phase 7 baseline — stellar variability characterisation.

    Lomb-Scargle period search plus robust amplitude and RMS. This is
    the honest classical baseline for variable stars (Wolf-Rayet
    candidates, pulsators, eclipsing binaries). NOTE: variability targets
    are NOT flattened — the detrender would erase the signal.

    min_period / max_period (days) bound the search. Bounding matters for
    real data: an unbounded search over a multi-sector baseline latches
    onto low-frequency red noise / instrumental trends (a Wolf-Rayet star
    that varies on ~2 d can otherwise return a ~50 d systematic). Defaults
    keep it to 0.1 d .. min(20 d, half the baseline).
    """
    lc = lk.LightCurve(time=time, flux=flux)
    baseline = float(np.ptp(np.asarray(time, dtype=float)))
    lo = 0.1 if min_period is None else min_period
    hi = min(20.0, 0.5 * baseline) if max_period is None else max_period
    kw = {}
    if lo:
        kw["minimum_period"] = lo
    if hi and hi > lo:
        kw["maximum_period"] = hi
    pg = lc.to_periodogram(**kw)      # Lomb-Scargle by default

    amplitude = float((np.percentile(flux, 95) - np.percentile(flux, 5)) / 2)
    return {
        "method": "variability",
        "period_days": float(pg.period_at_max_power.value),
        "t0": None,
        "duration_days": None,
        "depth": None,
        "rp_over_rstar": None,
        "amplitude": amplitude,
        "rms": float(np.std(flux)),
    }
