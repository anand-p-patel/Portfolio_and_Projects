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
