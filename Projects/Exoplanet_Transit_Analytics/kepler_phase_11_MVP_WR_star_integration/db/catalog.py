"""
NASA Exoplanet Archive candidate catalogues — unconfirmed objects that
are *still being vetted* (as opposed to the confirmed planets the
pipeline has results for).

Standard library only, so this is safe to import in the lightweight
dashboard (no torch / lightkurve). Network access is required; callers
should wrap these in a try/except and cache the result.

  Kepler -> KOI cumulative table, koi_disposition = 'CANDIDATE'
  TESS   -> TOI table, tfopwg_disp = 'PC' (planet candidate)
"""

import json
import urllib.parse
import urllib.request

TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

# Curated Wolf-Rayet stars for the Phase 7-full variability demo. WR stars
# are their own "mission" in the dashboard: they aren't in the exoplanet
# catalogues, their TESS/TIC headers carry wrong stellar parameters (the
# hot WR is blended with cooler neighbours), and their variability periods
# collide with instrumental red noise. So each carries LITERATURE Teff (K),
# radius (R_sun) and period (days) — fixing the star portrait and seeding a
# bounded period search. Chosen to span the coherence range the SHO-PINN's
# quality factor Q measures: an eclipsing binary (coherent) to a
# period-wandering wind (stochastic).
WR_STARS = [
    {"name": "WR 139 (V444 Cyg)", "ident": "HD 193576", "teff": 50000,
     "radius": 8.0, "period_days": 4.212,
     "note": "WN5+O6 eclipsing binary — coherent (expect high Q)"},
    {"name": "WR 134", "ident": "HD 191765", "teff": 63000,
     "radius": 6.6, "period_days": 2.27,
     "note": "WN6 — corotating interaction region, quasi-periodic"},
    {"name": "WR 6 (EZ CMa)", "ident": "HD 50896", "teff": 89000,
     "radius": 2.65, "period_days": 3.766,
     "note": "WN4 — famously period-wandering wind (expect low Q)"},
    {"name": "WR 136", "ident": "HD 192163", "teff": 70000,
     "radius": 4.9, "period_days": 4.5,
     "note": "WN6 — clumped wind variability"},
]

WR_BY_NAME = {s["name"]: s for s in WR_STARS}


def _query(adql, timeout=60):
    url = f"{TAP}?query={urllib.parse.quote(adql, safe='')}&format=json"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _kepler_host(kepler_name):
    """'Kepler-8 b' -> 'Kepler-8'; drop a trailing single-letter planet."""
    if not kepler_name:
        return None
    parts = kepler_name.split()
    if len(parts) >= 2 and len(parts[-1]) == 1 and parts[-1].isalpha():
        return " ".join(parts[:-1])
    return kepler_name


def fetch_catalog(mission, limit=6000):
    """
    The whole transit catalogue for a mission as a list of dicts:
        {"name", "status", "period_days", "prad_earth"}
    where status is "confirmed" (a confirmed transiting planet's host) or
    "candidate" (an unconfirmed object still being vetted).

      Kepler -> KOI cumulative table (CONFIRMED hosts + CANDIDATE KOIs)
      TESS   -> TOI table (CP/KP confirmed hosts + PC candidates)

    Deduplicated on name, confirmed winning over candidate. Raises on a
    network/HTTP error so the caller can fall back to local targets.
    """
    m = (mission or "").strip().lower()
    rows = []

    if m == "kepler":
        adql = (f"select top {limit} kepoi_name,kepler_name,koi_disposition,"
                "koi_period,koi_prad from cumulative where koi_disposition "
                "in ('CONFIRMED','CANDIDATE')")
        for r in _query(adql):
            if r.get("koi_disposition") == "CONFIRMED":
                name = _kepler_host(r.get("kepler_name"))
                status = "confirmed"
            else:
                name = r.get("kepoi_name")
                status = "candidate"
            if name:
                rows.append({"name": name, "status": status,
                             "period_days": r.get("koi_period"),
                             "prad_earth": r.get("koi_prad")})

    elif m == "tess":
        adql = (f"select top {limit} toi,tfopwg_disp,pl_orbper,pl_rade "
                "from toi where tfopwg_disp in ('CP','KP','PC')")
        for r in _query(adql):
            toi = r.get("toi")
            if r.get("tfopwg_disp") in ("CP", "KP"):
                name = f"TOI-{str(toi).split('.')[0]}"
                status = "confirmed"
            else:
                name = f"TOI-{toi}"
                status = "candidate"
            rows.append({"name": name, "status": status,
                         "period_days": r.get("pl_orbper"),
                         "prad_earth": r.get("pl_rade")})

    # Dedup on name; a confirmed row beats a candidate one.
    best = {}
    for r in rows:
        cur = best.get(r["name"])
        if cur is None or (cur["status"] == "candidate"
                           and r["status"] == "confirmed"):
            best[r["name"]] = r
    return sorted(best.values(), key=lambda r: r["name"])
