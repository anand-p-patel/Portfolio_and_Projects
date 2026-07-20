"""
Phase 1 — Data ingestion.

Downloads light curves from the MAST archive via lightkurve.
Requires internet access (mast.stsci.edu).
"""

import lightkurve as lk


def fetch_light_curve(target_id: str, mission: str = "Kepler"):
    """
    Search MAST and download a light curve for the given target.

    Parameters
    ----------
    target_id : str
        e.g. "Kepler-8" or "KIC 6922244"
    mission : str
        "Kepler", "K2", or "TESS". Parameterised now so the Phase 6
        telescope-adapter layer is a config change, not a rewrite.

    Returns
    -------
    lightkurve.LightCurve with NaNs removed, or None if nothing found.

    Notes
    -----
    - Downloads only the FIRST available quarter/sector (~90 days for
      Kepler). Phase 5 improvement: use .download_all().stitch() to get
      every quarter — more transits means better PINN fits.
    """
    search_result = lk.search_lightcurve(target_id, mission=mission)
    if len(search_result) == 0:
        return None

    lc = search_result[0].download()
    return lc.remove_nans()


def get_stellar_params(lc):
    """
    Pull the host star's effective temperature (K) and radius (R_sun)
    from the light curve's FITS header metadata. Kepler files carry
    TEFF and RADIUS from the Kepler Input Catalog; TESS files carry
    the same keys from the TESS Input Catalog. Either value may be
    None if the archive lacks it — downstream rendering degrades
    gracefully.
    """
    meta = getattr(lc, "meta", None) or {}
    teff = meta.get("TEFF")
    radius = meta.get("RADIUS")
    try:
        teff = float(teff) if teff is not None else None
    except (TypeError, ValueError):
        teff = None
    try:
        radius = float(radius) if radius is not None else None
    except (TypeError, ValueError):
        radius = None
    return teff, radius
