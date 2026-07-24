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


def _robust_sigma(x):
    """MAD-based per-point scatter, resistant to outliers."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return np.nan
    return 1.4826 * np.median(np.abs(x - np.median(x)))


def _is_subharmonic(time, flux, period, t0, duration, k,
                    min_frac: float = 0.5, min_snr: float = 3.0,
                    min_pts: int = 5):
    """
    Is `period` a k× harmonic alias whose true fundamental is period / k?

    BLS power at an integer harmonic k·P_true rivals the power at P_true —
    and on a long baseline the coarse grid smears the (shorter) fundamental,
    so BLS locks onto the harmonic. Folding at such a `period`, the real
    transits land not only at phase 0 but at every sub-position j·period/k
    (j = 1..k-1). So: fold at `period` and ask whether ALL k sub-positions
    hold a real, comparable-depth, significant transit. If they do, the
    fundamental is period / k and `period` is an alias.

    A clean fundamental fails this at every k (the intermediate phases are
    empty baseline), so run_bls is unchanged on correctly-recovered targets.
    """
    Pc = period / k
    half = 0.5 * duration
    ph = (np.asarray(time, dtype=float) - t0) % period    # [0, period)
    depths, counts = [], []
    near_any = np.zeros(ph.shape[0], dtype=bool)
    for j in range(k):
        c = (j * Pc) % period
        d = np.abs(((ph - c + 0.5 * period) % period) - 0.5 * period)
        sel = d < half
        if int(sel.sum()) < min_pts:
            return False
        depths.append(1.0 - np.median(flux[sel]))
        counts.append(int(sel.sum()))
        near_any |= d < 1.5 * half
    depths = np.asarray(depths)
    counts = np.asarray(counts, dtype=float)
    if np.any(depths <= 0) or depths.max() <= 0:
        return False
    if depths.min() / depths.max() < min_frac:        # depths inconsistent
        return False
    sigma = _robust_sigma(flux[~near_any])            # out-of-transit noise
    if not (np.isfinite(sigma) and sigma > 0):
        return False
    snr = depths * np.sqrt(counts) / sigma
    return bool(np.all(snr >= min_snr))


def run_bls(time, flux, min_period: float = 0.5, max_period: float = 15.0,
            n_periods: int = 5000, harmonic_check: bool = True, kmax: int = 8):
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
      Stage 3 — harmonic disambiguation (harmonic_check): the peak may be
                an integer harmonic k·P_true whose (shorter) fundamental the
                coarse grid smeared away. Test sub-harmonics period/k; if
                every sub-position holds a real transit, adopt the smallest
                such fundamental and re-refine. See _is_subharmonic.

    Scope of Stage 3: it corrects only the too-LONG direction — a peak at
    k·P_true, recovered as period/k. It does NOT test super-harmonics
    k·period, so a peak that is itself a *sub*-harmonic of a longer signal
    is left unchanged. Those longer fundamentals are typically outside
    [min_period, max_period] anyway. Kepler-16 (13.69 d = 1/3 of the 41 d
    stellar eclipse) and Kepler-9 (9.61 d = 1/2 of 19.24 d) are exactly this
    case: their true fundamentals lie beyond max_period, so Stage 3 cannot
    reach them — their stored periods remain aliased (out of scope here),
    not corrected. (Kepler-16 is separately rejected by vetting for an
    unrelated reason — its box-fit Rp/R* trips the stellar-companion cap —
    which does not make its stored 13.69 d period right.)

    Bounded (~45k evaluations total), fast, and cadence-agnostic.

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
    period = float(res.period[best])
    t0 = float(res.transit_time[best])
    duration = float(res.duration[best])
    depth = float(res.depth[best])

    # Stage 3: harmonic disambiguation. Prefer the LARGEST k that passes —
    # the smallest self-consistent fundamental — then re-refine at it.
    if harmonic_check:
        for k in range(kmax, 1, -1):
            Pc = period / k
            if Pc < min_period:
                continue
            # Sub-transit windows sit Pc apart with half-width 0.5·duration;
            # if Pc is not comfortably larger than the window, they overlap
            # and every phase reads as in-transit. min_period (0.5 d) and the
            # 0.30 d duration cap normally keep them apart, but that invariant
            # otherwise lives implicitly in two unrelated constants — enforce
            # it here so the sub-harmonic test is never run on overlapping
            # windows.
            if Pc <= 2.0 * duration:
                continue
            if _is_subharmonic(time, flux, period, t0, duration, k):
                lo2 = max(Pc - 5 * step, 1e-3)
                fine2 = np.linspace(lo2, Pc + 5 * step, 20000)
                res2 = bls.power(fine2, BLS_DURATIONS)
                b2 = int(np.argmax(res2.power))
                period = float(res2.period[b2])
                t0 = float(res2.transit_time[b2])
                duration = float(res2.duration[b2])
                depth = float(res2.depth[b2])
                break

    # Physics: Delta F = (Rp / R*)^2  =>  Rp/R* = sqrt(Delta F)
    rp_over_rstar = float(np.sqrt(max(depth, 0.0)))

    return {
        "method": "bls",
        "period_days": period,
        "t0": t0,
        "duration_days": duration,
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
