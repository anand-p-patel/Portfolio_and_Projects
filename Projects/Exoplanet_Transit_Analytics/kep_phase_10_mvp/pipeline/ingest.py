"""
Phase 1 — Data ingestion.

Downloads light curves from the MAST archive via lightkurve.
Requires internet access (mast.stsci.edu).
"""

import numpy as np
import lightkurve as lk

# Preferred data-reduction pipeline per mission, in priority order. MAST
# returns products from many authors (official + community); stitching
# across different pipelines mixes incompatible systematics, so we lock
# onto one. "Kepler"/"K2" are the official products; "SPOC" is TESS's
# 2 min official pipeline (best for shallow transits), then the FFI-based
# "TESS-SPOC", then the community "QLP" as a last resort.
AUTHOR_PREFERENCE = {
    "Kepler": ["Kepler"],
    "K2": ["K2"],
    "TESS": ["SPOC", "TESS-SPOC", "QLP"],
}


def fetch_light_curve(target_id: str, mission: str = "Kepler",
                      quarters=None):
    """
    Search MAST and download a light curve for the given target.

    Parameters
    ----------
    target_id : str
        e.g. "Kepler-8" or "KIC 6922244"
    mission : str
        "Kepler", "K2", or "TESS". Parameterised now so the Phase 6
        telescope-adapter layer is a config change, not a rewrite.
    quarters : int or None
        How many quarters/sectors to download and stitch. None (default)
        downloads every available quarter; an integer N takes the first
        N search results.

    Returns
    -------
    lightkurve.LightCurve with NaNs removed, or None if nothing found.

    Notes
    -----
    - Phase 5b: downloads ALL available quarters and stitches them into
      a single light curve. One Kepler quarter is ~90 days (~8 transits
      for a 3.5 d period); the full mission is ~4 years, so stacking
      every quarter in the phase fold deepens transit SNR and is the
      primary fix for the depth underestimate on real targets.
    - stitch() normalizes each quarter before concatenating, so the
      per-quarter flux-level offsets don't inject false trends.
    """
    search_result = lk.search_lightcurve(target_id, mission=mission)
    if len(search_result) == 0:
        return None

    # MAST returns many products per target — different pipelines and
    # both short- and long-cadence sampling. Narrow to one pipeline and
    # one cadence so the stitch doesn't mix incompatible reductions or
    # double-cover epochs (1 quarter of Kepler 60 s ≈ a whole mission of
    # 1800 s LC). See _select_products.
    search_result = _select_products(search_result, mission)

    selected = search_result if quarters is None else search_result[:quarters]
    collection = selected.download_all()
    if collection is None or len(collection) == 0:
        return None

    # A single segment needs no stitching; stitch() would normalize it
    # but the flatten step downstream normalizes anyway.
    lc = collection[0] if len(collection) == 1 else collection.stitch()
    return lc.remove_nans()


def _select_products(search_result, mission="Kepler"):
    """
    Narrow a SearchResult to one pipeline author and one cadence so a
    multi-quarter/sector stitch is self-consistent:

    1. Keep the highest-priority AUTHOR_PREFERENCE pipeline that's present
       (e.g. TESS 'SPOC' over community products).
    2. Within that, keep the LONGEST exposure time. For Kepler this is
       the 1800 s long cadence that spans every quarter (short cadence is
       split into far more files and would balloon the point count); for
       TESS 'SPOC' this is the 120 s product, the best for shallow
       transits. A single cadence keeps the stitch from double-covering
       epochs.

    Falls back gracefully if the author/exptime columns are missing.
    """
    table = search_result.table
    n = len(search_result)
    keep = np.ones(n, dtype=bool)

    if "author" in table.colnames:
        authors = [str(a) for a in table["author"]]
        for preferred in AUTHOR_PREFERENCE.get(mission, []):
            match = np.array([a == preferred for a in authors])
            if match.any():
                keep &= match
                break

    if "exptime" in table.colnames:
        try:
            exps = np.array([float(e) for e in table["exptime"]])
            longest = exps[keep].max()
            keep &= (exps == longest)
        except (ValueError, TypeError):
            pass

    idx = list(np.nonzero(keep)[0])
    return search_result[idx] if idx else search_result


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
