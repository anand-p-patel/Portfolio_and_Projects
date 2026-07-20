"""
Phase 2 — Cleaning & detrending (ETL layer).

Removes long-term instrument drift so the PINN sees pure transit physics.
"""

import numpy as np

# Nominal cadence per mission (minutes). Kepler/K2 long cadence is
# 29.4 min; TESS default short cadence is 2 min (10 min and 30 min FFI
# products also exist). This is a FALLBACK — measure_cadence_minutes()
# prefers the actual sampling in the light curve, which is exact and
# handles whichever TESS product was downloaded.
CADENCE_MINUTES = {"Kepler": 29.4, "K2": 29.4, "TESS": 2.0}


def measure_cadence_minutes(lc=None, mission=None):
    """
    Median time between cadences, in minutes. Measured from the light
    curve when available (exact, mission-agnostic); otherwise the
    per-mission CADENCE_MINUTES fallback (Kepler default).
    """
    if lc is not None:
        try:
            t = np.sort(np.asarray(lc.time.value, dtype=float))
            dt = np.median(np.diff(t))
            if np.isfinite(dt) and dt > 0:
                return float(dt) * 24 * 60
        except (AttributeError, ValueError, TypeError):
            pass
    return CADENCE_MINUTES.get(mission, 29.4)


def flatten_window_length(lc=None, mission=None,
                          window_days: float = 2.06, min_length: int = 51):
    """
    Savitzky-Golay window in *cadences* for a target physical detrend
    scale (default ~2 days, well above any planetary transit duration).

    window_length is a cadence count, so a fixed 101 is only right for
    Kepler's 29.4 min sampling — at TESS's 2 min cadence that same 101
    points spans just ~3.4 h and would fit (and erase) the transit. This
    converts a *duration* to the right cadence count for the mission.
    At 29.4 min the default returns 101, preserving Kepler behaviour.
    """
    cadence = measure_cadence_minutes(lc, mission)
    n = int(round(window_days * 24 * 60 / cadence))
    if n % 2 == 0:
        n += 1
    return max(n, min_length)


def flatten_light_curve(lc, window_length: int = 101, transit_mask=None):
    """
    Detrend a light curve with lightkurve's Savitzky-Golay flatten.

    Parameters
    ----------
    lc : lightkurve.LightCurve
    window_length : int
        Rolling window (in cadences) used to model the slow drift.
        Kepler long cadence = 29.4 min, so 101 points ~= 2.06 days.
    transit_mask : boolean ndarray, optional
        True for in-transit cadences (Phase 4b). These points are
        excluded from the Savitzky-Golay trend fit — the filter models
        the drift from the out-of-transit baseline only and interpolates
        across the gaps, so it never erodes the transit floor. The masked
        points are still returned (divided by the interpolated trend);
        only the *fit* ignores them.

    Returns
    -------
    (time, flux) : tuple of clean float64 numpy arrays.

    PHYSICS CAUTION
    ---------------
    flatten() does not know the transit dips are real astrophysics.
    If window_length is short relative to the transit duration, an
    unmasked filter partially removes the transit itself — corrupting
    the depth (Delta F) that the PINN fits. Passing transit_mask removes
    this bias entirely (Phase 4b); without it, keep the window at least
    ~10x the transit duration (for a ~4 h transit, 101 points ~= 2 days).
    """
    if transit_mask is not None:
        flattened_lc = lc.flatten(window_length=window_length,
                                  mask=transit_mask)
    else:
        flattened_lc = lc.flatten(window_length=window_length)

    final_time = np.asarray(flattened_lc.time.value, dtype=float)
    final_flux = np.asarray(flattened_lc.flux.value, dtype=float)

    return final_time, final_flux
