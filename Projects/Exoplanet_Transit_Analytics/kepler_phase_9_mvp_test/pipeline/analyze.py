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


def run_bls(time, flux, min_period: float = 0.5, max_period: float = 15.0):
    """
    Run a Box Least Squares period search on a flattened light curve.

    Returns
    -------
    dict with keys:
        period_days, t0, duration_days, depth, rp_over_rstar, method
    """
    lc = lk.LightCurve(time=time, flux=flux)

    period_grid = np.linspace(min_period, max_period, 5000)
    pg = lc.to_periodogram(method="bls", period=period_grid)

    depth = float(pg.depth_at_max_power)
    # Physics: Delta F = (Rp / R*)^2  =>  Rp/R* = sqrt(Delta F)
    rp_over_rstar = float(np.sqrt(max(depth, 0.0)))

    return {
        "method": "bls",
        "period_days": float(pg.period_at_max_power.value),
        "t0": float(pg.transit_time_at_max_power.value),
        "duration_days": float(pg.duration_at_max_power.value),
        "depth": depth,
        "rp_over_rstar": rp_over_rstar,
    }


def run_variability(time, flux):
    """
    Phase 7 baseline — stellar variability characterisation.

    Lomb-Scargle period search plus robust amplitude and RMS. This is
    the honest classical baseline for variable stars (Wolf-Rayet
    candidates, pulsators, eclipsing binaries); a WR-specific physics
    loss is future work layered on top, exactly as the PINN layered on
    BLS. NOTE: variability targets are NOT flattened — the detrender
    would erase the very signal being measured.
    """
    lc = lk.LightCurve(time=time, flux=flux)
    pg = lc.to_periodogram()          # Lomb-Scargle by default

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
