"""
Phase 10 — transit vetting / false-positive tests.

A dip is not a planet. These are the standard checks that separate a
planet candidate from an eclipsing binary (EB), a blend, or noise. The
light-curve tests (odd/even, secondary, SNR) are pure NumPy and run from
the stored arrays — the dashboard computes them live. The centroid test
needs pixel-level data (Target Pixel Files) and is opt-in.

Disposition logic (transit context):
  - SNR below threshold            -> "low_snr"  (not significant)
  - any false-positive flag raised  -> "false_positive"
  - otherwise                       -> "candidate"

References: Batalha et al. 2013 (Kepler vetting), the standard
odd/even and secondary-eclipse EB diagnostics.
"""

import numpy as np

# Thresholds. Each false-positive test gates on BOTH statistical
# significance AND relative size: on high-SNR data a negligible
# systematic can be "many sigma" yet a tiny fraction of the depth, which
# would wrongly condemn a real planet. A true EB fails on both.
SNR_MIN = 7.1               # Kepler's canonical detection floor
ODDEVEN_SIGMA_MIN = 3.0     # odd/even must differ this significantly …
ODDEVEN_FRAC_MIN = 0.5      # … AND by >50% of the transit depth
SECONDARY_SNR_MIN = 5.0     # secondary must be this significant to matter …
SECONDARY_FRAC_MIN = 0.3    # … >30% as deep as primary  -> unequal-eclipse EB
SECONDARY_FRAC_EQUAL = 0.7  # … >70% (≈equal)            -> period alias / sym. EB
MAX_PLANET_RATIO = 0.18     # Rp/R* above this is a star, not a planet
CENTROID_SIGMA_MIN = 3.0    # centroid shift must be this significant …
CENTROID_SHIFT_MIN_PX = 0.05  # … AND this large (a fraction of a pixel)


def _robust_sigma(x):
    """MAD-based per-point scatter, resistant to outliers."""
    if x.size == 0:
        return np.nan
    med = np.median(x)
    return 1.4826 * np.median(np.abs(x - med))


def _phase_days(time, period, t0):
    """Signed time from the nearest mid-transit, in days, in [-P/2, P/2)."""
    return ((time - t0 + 0.5 * period) % period) - 0.5 * period


def vet_lightcurve(time, flux, period, t0, duration):
    """
    Run the light-curve false-positive tests and return a report dict:

        snr, depth, n_transits,
        odd_depth, even_depth, oddeven_sigma,
        secondary_depth, secondary_snr,
        flags (list of human-readable strings),
        disposition ("candidate" | "false_positive" | "low_snr")
    """
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    ph = _phase_days(time, period, t0)

    half = 0.5 * duration
    in_transit = np.abs(ph) < half
    out = np.abs(ph) > 1.5 * half           # clean baseline, clear of transit
    sigma = _robust_sigma(flux[out])         # per-point noise

    n_in = int(in_transit.sum())
    depth = float(1.0 - np.median(flux[in_transit])) if n_in else float("nan")

    # --- Transit SNR: depth measured over N in-transit points ---
    snr = (depth * np.sqrt(n_in) / sigma
           if n_in and sigma and np.isfinite(sigma) else float("nan"))

    # --- Odd/even consistency: EBs alias to half the true period ---
    epoch = np.round((time - t0) / period).astype(int)
    odd = in_transit & (epoch % 2 != 0)
    even = in_transit & (epoch % 2 == 0)
    n_odd, n_even = int(odd.sum()), int(even.sum())
    odd_depth = float(1.0 - np.median(flux[odd])) if n_odd else float("nan")
    even_depth = float(1.0 - np.median(flux[even])) if n_even else float("nan")
    if n_odd and n_even and sigma:
        err = sigma * np.sqrt(1.0 / n_odd + 1.0 / n_even)
        oddeven_sigma = float(abs(odd_depth - even_depth) / err)
    else:
        oddeven_sigma = float("nan")

    # --- Secondary eclipse near phase 0.5 (a stellar companion) ---
    sec = (0.5 * period - np.abs(ph)) < half   # within a duration of phase 0.5
    n_sec = int(sec.sum())
    secondary_depth = float(1.0 - np.median(flux[sec])) if n_sec else float("nan")
    secondary_snr = (secondary_depth * np.sqrt(n_sec) / sigma
                     if n_sec and sigma else float("nan"))

    rp_over_rstar = float(np.sqrt(depth)) if np.isfinite(depth) and depth > 0 \
        else float("nan")

    # --- Flags + disposition. Each flag is tagged "fp" (a clear false
    #     positive) or "review" (ambiguous — a human/second pass needed). ---
    flags = []  # list of (severity, message)

    oddeven_frac = (abs(odd_depth - even_depth) / depth
                    if np.isfinite(depth) and depth > 0 else float("nan"))
    if (np.isfinite(oddeven_sigma) and oddeven_sigma > ODDEVEN_SIGMA_MIN
            and np.isfinite(oddeven_frac) and oddeven_frac > ODDEVEN_FRAC_MIN):
        flags.append(("fp",
                      f"odd/even depth mismatch ({oddeven_sigma:.0f}σ, "
                      f"{oddeven_frac * 100:.0f}% of depth) — eclipsing "
                      "binary at 2× the folded period"))

    secondary_frac = (secondary_depth / depth
                      if np.isfinite(depth) and depth > 0 else float("nan"))
    if (np.isfinite(secondary_snr) and secondary_snr > SECONDARY_SNR_MIN
            and np.isfinite(secondary_frac)):
        if secondary_frac > SECONDARY_FRAC_EQUAL:
            flags.append(("review",
                          f"secondary as deep as the primary "
                          f"({secondary_frac * 100:.0f}%) — the period is "
                          "likely 2× the true value (re-fold at P/2), or a "
                          "symmetric eclipsing binary"))
        elif secondary_frac > SECONDARY_FRAC_MIN:
            flags.append(("fp",
                          f"deep secondary eclipse ({secondary_snr:.0f}σ, "
                          f"{secondary_frac * 100:.0f}% of primary) — a "
                          "self-luminous stellar companion"))

    if np.isfinite(rp_over_rstar) and rp_over_rstar > MAX_PLANET_RATIO:
        flags.append(("fp",
                      f"companion too large (Rp/R* = {rp_over_rstar:.2f}) — "
                      "a stellar radius ratio, not planetary"))

    severities = {sev for sev, _ in flags}
    if not (np.isfinite(snr) and snr >= SNR_MIN):
        disposition = "low_snr"
    elif "fp" in severities:
        disposition = "false_positive"
    elif "review" in severities:
        disposition = "review"
    else:
        disposition = "candidate"

    return {
        "snr": snr, "depth": depth, "rp_over_rstar": rp_over_rstar,
        "n_transits": int(np.unique(epoch[in_transit]).size) if n_in else 0,
        "odd_depth": odd_depth, "even_depth": even_depth,
        "oddeven_sigma": oddeven_sigma,
        "secondary_depth": secondary_depth, "secondary_snr": secondary_snr,
        "flags": [msg for _, msg in flags], "disposition": disposition,
    }


def vet_centroid(target_id, mission, period, t0, duration,
                 max_products=1):
    """
    Centroid-motion test (opt-in; needs Target Pixel Files). If the flux
    centroid shifts during transit, the eclipse is on a *different* star
    in the aperture — a background eclipsing binary / blend, not a transit
    on the target.

    Returns a dict {centroid_shift_pixels, centroid_sigma, centroid_pass,
    note} or {note: ...} on failure. Imports lightkurve lazily.
    """
    try:
        import lightkurve as lk
    except Exception as exc:
        return {"note": f"lightkurve unavailable: {exc}"}

    try:
        sr = lk.search_targetpixelfile(target_id, mission=mission)
        if len(sr) == 0:
            return {"note": "no target pixel file found"}
        tpf = sr[:max_products].download_all()
        tpf = tpf[0] if tpf is not None and len(tpf) else None
        if tpf is None:
            return {"note": "target pixel file download failed"}

        col, row = tpf.estimate_centroids()
        t = np.asarray(tpf.time.value, dtype=float)
        col = np.asarray(col.value, dtype=float)
        row = np.asarray(row.value, dtype=float)
        good = np.isfinite(col) & np.isfinite(row)
        t, col, row = t[good], col[good], row[good]

        ph = _phase_days(t, period, t0)
        half = 0.5 * duration
        intr = np.abs(ph) < half
        out = np.abs(ph) > 1.5 * half
        if intr.sum() < 3 or out.sum() < 3:
            return {"note": "too few cadences for centroid test"}

        d_col = np.median(col[intr]) - np.median(col[out])
        d_row = np.median(row[intr]) - np.median(row[out])
        shift = float(np.hypot(d_col, d_row))
        # scatter of the out-of-transit centroid -> significance
        sig = np.hypot(_robust_sigma(col[out]), _robust_sigma(row[out]))
        sig_mean = float(sig / np.sqrt(max(int(intr.sum()), 1)))
        signif = shift / sig_mean if sig_mean else float("nan")
        # A blend must move the centroid both significantly AND by a
        # meaningful fraction of a pixel — a tiny, formally-significant
        # jitter on a bright star is not a blend.
        failed = bool(np.isfinite(signif) and signif > CENTROID_SIGMA_MIN
                      and shift > CENTROID_SHIFT_MIN_PX)
        return {
            "centroid_shift_pixels": shift,
            "centroid_sigma": float(signif),
            "centroid_pass": not failed,
            "note": (f"centroid shifts {shift:.2f} px ({signif:.0f}σ) "
                     "in-transit — possible blend / background eclipsing "
                     "binary" if failed else
                     f"centroid stable in-transit ({shift:.3f} px)"),
        }
    except Exception as exc:
        return {"note": f"centroid test failed: {exc}"}


DISPOSITION_LABEL = {
    "candidate": "Planet candidate",
    "review": "Needs review",
    "false_positive": "Likely false positive",
    "low_snr": "Not significant (low SNR)",
}
