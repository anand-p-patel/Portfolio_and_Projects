"""
Phase 2 — Cleaning & detrending (ETL layer).

Removes long-term instrument drift so the PINN sees pure transit physics.
"""

import numpy as np


def flatten_light_curve(lc, window_length: int = 101):
    """
    Detrend a light curve with lightkurve's Savitzky-Golay flatten.

    Parameters
    ----------
    lc : lightkurve.LightCurve
    window_length : int
        Rolling window (in cadences) used to model the slow drift.
        Kepler long cadence = 29.4 min, so 101 points ~= 2.06 days.

    Returns
    -------
    (time, flux) : tuple of clean float64 numpy arrays.

    PHYSICS CAUTION
    ---------------
    flatten() does not know the transit dips are real astrophysics.
    If window_length is short relative to the transit duration, the
    filter partially removes the transit itself — corrupting the depth
    (Delta F) that the PINN fits. Rule of thumb: keep the window at
    least ~10x the transit duration. For a ~4 h transit, 101 points
    (~2 days) is safe. TODO (Phase 4 refinement): mask in-transit
    points before flattening for a bias-free depth.
    """
    flattened_lc = lc.flatten(window_length=window_length)

    final_time = np.asarray(flattened_lc.time.value, dtype=float)
    final_flux = np.asarray(flattened_lc.flux.value, dtype=float)

    return final_time, final_flux
