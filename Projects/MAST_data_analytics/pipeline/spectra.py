"""
Phase 11 (IN PROGRESS) — JWST / HST Wolf-Rayet spectral data.

A SEPARATE capability from the light-curve pipeline. JWST and HST are
pointed spectroscopy/imaging observatories, not time-domain surveys — MAST
returns no *light curves* for them (see db.catalog notes), so the transit
and SHO-PINN machinery does not apply here. This module fetches 1D
*spectra* from MAST via astroquery and parses them to (wavelength, flux)
for a spectral viewer.

De-risk findings (verified against real data):
  - Wolf-Rayet stars DO have JWST + HST spectra in MAST, e.g. WR 140
    (JWST MIRI), WR 137 (JWST NIRSpec/MIRI IFU), WR 6 / EZ CMa, WR 136 and
    gamma Vel (HST STIS/GHRS).
  - JWST 1D spectra ('X1D' products) use a standard EXTRACT1D binary table
    with WAVELENGTH (um) and FLUX (Jy) columns — parses cleanly.
  - HST is heterogeneous (STIS x1d, GHRS, FOS; some modes give only 2D
    spectra). Handled best-effort; robust per-instrument HST parsing is
    still TODO.

Dependencies: astroquery + astropy (already present via lightkurve). This
is pipeline-side only; the lightweight dashboard would call it lazily.
"""

import os

import numpy as np

# Bundled spectra live here as small .npz files so the dashboard can show
# them offline (same pattern as data/processed light curves).
SPECTRA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "spectra")

# Prominent Wolf-Rayet emission lines (rest wavelength in microns). WR
# spectra are dominated by broad emission from the wind: He II and N lines
# in WN stars, C IV/C III in WC stars, plus IR recombination and forbidden
# lines that fall in the JWST range. The viewer marks whichever lie inside
# a given spectrum's wavelength coverage.
WR_LINES = [
    # UV (HST)
    ("N V", 0.1240), ("Si IV", 0.1400), ("N IV]", 0.1486),
    ("C IV", 0.1550), ("He II", 0.1640), ("N III]", 0.1750),
    ("C III]", 0.1909),
    # optical
    ("N IV", 0.4058), ("N V", 0.4604), ("He II", 0.4686),
    ("C III", 0.5696), ("C IV", 0.5808), ("He I", 0.5876),
    # near-IR
    ("C III", 0.9711), ("He II", 1.0124), ("He I", 1.0830),
    ("He II", 1.1630), ("He I", 2.0587), ("He II", 2.1885),
    # mid-IR (JWST)
    ("Brα", 4.052), ("[S IV]", 10.51), ("[Ne II]", 12.81),
]


def find_spectra(objectname, collection="JWST", instrument=None):
    """
    Query MAST for 1D-spectrum observations of a target. Metadata only —
    no downloads. Returns an astropy Table of observations (possibly
    empty). `collection` is "JWST" or "HST"; `instrument` optionally
    narrows (e.g. "MIRI/SLIT", "STIS/CCD").
    """
    from astroquery.mast import Observations
    crit = dict(objectname=objectname, obs_collection=collection,
                dataproduct_type="spectrum")
    if instrument:
        crit["instrument_name"] = instrument
    return Observations.query_criteria(**crit)


def _find_x1d(obs_table, max_obs=8):
    """
    Scan observations for one carrying a 1D extracted spectrum ('X1D' —
    JWST and HST STIS 1D; 'SX1' — some HST). Returns (one-row Table of the
    smallest X1D product, instrument_name) or (None, None). Scans up to
    max_obs because the X1D isn't always the first observation.
    """
    from astroquery.mast import Observations
    for i in range(min(max_obs, len(obs_table))):
        products = Observations.get_product_list(obs_table[i:i + 1])
        x1d = Observations.filter_products(
            products, productSubGroupDescription=["X1D", "SX1"],
            extension="fits")
        if len(x1d):
            j = int(np.argmin(np.asarray(x1d["size"], dtype=float)))
            inst = str(obs_table[i]["instrument_name"])
            return x1d[[j]], inst
    return None, None


def parse_spectrum(path):
    """
    Parse a 1D-spectrum FITS file to (wavelength, flux, wave_unit,
    flux_unit). Finds the first binary table carrying WAVELENGTH and FLUX
    columns (JWST EXTRACT1D, HST STIS x1d). Flattens per-order 2D arrays
    and drops non-finite samples. Returns arrays sorted by wavelength.
    """
    from astropy.io import fits
    with fits.open(path) as hdul:
        for hdu in hdul:
            cols = getattr(getattr(hdu, "data", None), "columns", None)
            names = set(cols.names) if cols is not None else set()
            if {"WAVELENGTH", "FLUX"} <= names:
                wave = np.asarray(hdu.data["WAVELENGTH"], dtype=float).ravel()
                flux = np.asarray(hdu.data["FLUX"], dtype=float).ravel()
                wunit = getattr(hdu.columns["WAVELENGTH"], "unit", None)
                funit = getattr(hdu.columns["FLUX"], "unit", None)
                good = np.isfinite(wave) & np.isfinite(flux)
                wave, flux = wave[good], flux[good]
                order = np.argsort(wave)
                return (wave[order], flux[order],
                        str(wunit or "?"), str(funit or "?"))
    raise ValueError(f"no WAVELENGTH/FLUX table found in {path}")


def fetch_spectrum(objectname, collection="JWST", instrument=None,
                   download_dir=None):
    """
    Fetch and parse one 1D spectrum for a target (the first observation's
    smallest X1D product). Returns a dict:
        {wavelength, flux, wave_unit, flux_unit, filename, collection,
         instrument} or None if nothing is available.

    Network + disk: downloads a (usually small) FITS file into
    download_dir, cached by astroquery.
    """
    obs = find_spectra(objectname, collection=collection,
                       instrument=instrument)
    if len(obs) == 0:
        return None

    kwargs = {}
    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
        kwargs["download_dir"] = download_dir

    # Preferred path: a single 1D-extracted product (JWST EXTRACT1D, HST
    # STIS X1D) that carries WAVELENGTH + FLUX in one table.
    smallest, inst = _find_x1d(obs)
    if smallest is not None:
        from astroquery.mast import Observations
        path = Observations.download_products(smallest, **kwargs)["Local Path"][0]
        wave, flux, wunit, funit = parse_spectrum(path)
        return {
            "wavelength": wave, "flux": flux,
            "wave_unit": wunit, "flux_unit": funit,
            "filename": os.path.basename(path), "collection": collection,
            "instrument": inst or instrument or "",
        }

    # Fallback for HST GHRS, whose calibrated wavelength (C0F) and flux
    # (C1F) live in separate files.
    if collection == "HST":
        return _fetch_ghrs(obs, kwargs)
    return None


def _fetch_ghrs(obs, download_kwargs):
    """Pair a GHRS C0F (wavelength) and C1F (flux) into one spectrum."""
    from astroquery.mast import Observations
    from astropy.io import fits
    for i in range(min(12, len(obs))):
        pl = Observations.get_product_list(obs[i:i + 1])
        c0 = Observations.filter_products(
            pl, productSubGroupDescription=["C0F"], extension="fits")
        c1 = Observations.filter_products(
            pl, productSubGroupDescription=["C1F"], extension="fits")
        if len(c0) == 0 or len(c1) == 0:
            continue
        p0 = Observations.download_products(
            c0[[0]], **download_kwargs)["Local Path"][0]
        p1 = Observations.download_products(
            c1[[0]], **download_kwargs)["Local Path"][0]
        wave = np.asarray(fits.getdata(p0), dtype=float).ravel()
        flux = np.asarray(fits.getdata(p1), dtype=float).ravel()
        n = min(wave.size, flux.size)
        wave, flux = wave[:n], flux[:n]
        good = np.isfinite(wave) & np.isfinite(flux) & (wave > 0)
        wave, flux = wave[good], flux[good]
        order = np.argsort(wave)
        return {
            "wavelength": wave[order], "flux": flux[order],
            "wave_unit": "Angstrom", "flux_unit": "erg/s/cm2/Angstrom",
            "filename": os.path.basename(p1), "collection": "HST",
            "instrument": str(obs[i]["instrument_name"]),
        }
    return None


def _safe(name):
    return name.replace(" ", "_").replace("/", "_")


def save_spectrum(name, spec, spectra_dir=SPECTRA_DIR):
    """Persist a fetched spectrum to a bundled .npz for offline display."""
    os.makedirs(spectra_dir, exist_ok=True)
    path = os.path.join(spectra_dir, _safe(name) + ".npz")
    np.savez_compressed(
        path, wavelength=spec["wavelength"], flux=spec["flux"],
        wave_unit=spec["wave_unit"], flux_unit=spec["flux_unit"],
        collection=spec["collection"], instrument=spec.get("instrument", ""),
        filename=spec.get("filename", ""))
    return path


def load_spectrum(name, spectra_dir=SPECTRA_DIR):
    """Load a bundled spectrum as a dict, or None. NumPy only — safe to
    call from the lightweight dashboard (no astroquery)."""
    path = os.path.join(spectra_dir, _safe(name) + ".npz")
    if not os.path.exists(path):
        return None
    a = np.load(path)
    return {
        "wavelength": a["wavelength"], "flux": a["flux"],
        "wave_unit": str(a["wave_unit"]), "flux_unit": str(a["flux_unit"]),
        "collection": str(a["collection"]), "instrument": str(a["instrument"]),
        "filename": str(a["filename"]),
    }
