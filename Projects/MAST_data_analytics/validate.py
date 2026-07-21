"""
validate.py — compare pipeline results against the NASA Exoplanet Archive.

The pipeline measures the planet-to-star radius ratio Rp/R* two ways
(BLS box fit and the PINN). This script fetches the *published* Rp/R*
for the same targets from the NASA Exoplanet Archive and tabulates all
three side by side — the quantitative check that the pipeline is
correct, and the centrepiece validation table for the README.

The archive publishes planet radius (Earth or Jupiter radii) and stellar
radius (solar radii) separately, so we reconstruct the ratio:

    Rp/R* = R_planet / R_star           (same physical units)
          = (pl_rade * R_earth) / (st_rad * R_sun)

Usage
-----
    python validate.py --range Kepler 8 17
    python validate.py --targets Kepler-8 Kepler-10 Kepler-12
    python validate.py --range Kepler 8 17 --markdown   # emit a MD table

Targets must already be in the local DB (run run_pipeline.py first).
The archive query needs internet; everything else is offline.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request

from db import storage

# IAU nominal radii (2015 Resolution B3): equatorial R_earth and R_jup
# expressed as fractions of the nominal solar radius. These convert the
# archive's per-body radii into a dimensionless Rp/R*.
R_EARTH_OVER_R_SUN = 6.3781e6 / 6.957e8   # 0.009168
R_JUP_OVER_R_SUN = 7.1492e7 / 6.957e8     # 0.102762

ARCHIVE_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


def expand_range(prefix, start, end):
    """'Kepler', 8, 12 -> ['Kepler-8', ..., 'Kepler-12']."""
    if end < start:
        start, end = end, start
    return [f"{prefix}-{i}" for i in range(start, end + 1)]


def query_archive(hostname, timeout=30):
    """
    Return published planets for one host as a list of dicts:
        {"pl_name", "rp_over_rstar"}   (rp_over_rstar may be None)

    Uses pl_rade when present, falling back to pl_radj. Raises on a
    network/HTTP error so the caller can report the target as unchecked
    rather than silently wrong.
    """
    query = ("select pl_name,pl_rade,pl_radj,st_rad from pscomppars "
             f"where hostname='{hostname}'")
    url = f"{ARCHIVE_TAP}?query={urllib.parse.quote(query, safe='')}&format=json"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        rows = json.loads(resp.read().decode())

    planets = []
    for row in rows:
        st_rad = row.get("st_rad")
        rp_over_rstar = None
        if st_rad:
            if row.get("pl_rade") is not None:
                rp_over_rstar = row["pl_rade"] * R_EARTH_OVER_R_SUN / st_rad
            elif row.get("pl_radj") is not None:
                rp_over_rstar = row["pl_radj"] * R_JUP_OVER_R_SUN / st_rad
        planets.append({"pl_name": row.get("pl_name"),
                        "rp_over_rstar": rp_over_rstar})
    return planets


def primary_planet(planets):
    """
    The pipeline detects one dominant transit per target; BLS locks onto
    the highest-SNR signal, which scales with depth. Compare against the
    deepest (largest Rp/R*) published planet as the best-matched body.
    """
    withval = [p for p in planets if p["rp_over_rstar"] is not None]
    if not withval:
        return None
    return max(withval, key=lambda p: p["rp_over_rstar"])


def local_ratios(target_id):
    """(bls, pinn) Rp/R* from the local DB, each None if absent."""
    loaded = storage.load_target(target_id)
    if loaded is None:
        return None, None
    results = loaded["results"]
    bls = results.get("bls", {}).get("rp_over_rstar")
    pinn = results.get("pinn", {}).get("rp_over_rstar")
    return bls, pinn


def pct_diff(measured, published):
    """Signed percent difference of measured from published."""
    if measured is None or not published:
        return None
    return 100.0 * (measured - published) / published


def collect(targets):
    """Build one comparison row per target."""
    rows = []
    for target in targets:
        bls, pinn = local_ratios(target)
        published = None
        n_planets = 0
        note = ""
        try:
            planets = query_archive(target)
            n_planets = sum(1 for p in planets if p["rp_over_rstar"] is not None)
            prim = primary_planet(planets)
            if prim is not None:
                published = prim["rp_over_rstar"]
                if n_planets > 1:
                    note = f"{n_planets} planets; primary {prim['pl_name']}"
            elif planets:
                note = "no published radius"
            else:
                note = "not in archive"
        except Exception as exc:
            note = f"archive error: {exc}"
        rows.append({
            "target": target, "published": published,
            "bls": bls, "pinn": pinn,
            "bls_dpct": pct_diff(bls, published),
            "pinn_dpct": pct_diff(pinn, published),
            "note": note,
        })
    return rows


def _fmt(x, spec="{:.4f}"):
    return spec.format(x) if x is not None else "—"


def print_table(rows):
    """Aligned plain-text table for the terminal."""
    header = ("Target", "Published", "BLS", "ΔBLS%", "PINN", "ΔPINN%", "Note")
    widths = [12, 10, 9, 8, 9, 8, 28]
    line = "  ".join(h.ljust(w) for h, w in zip(header, widths))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        cells = [
            r["target"],
            _fmt(r["published"]),
            _fmt(r["bls"]),
            _fmt(r["bls_dpct"], "{:+.1f}"),
            _fmt(r["pinn"]),
            _fmt(r["pinn_dpct"], "{:+.1f}"),
            r["note"],
        ]
        print("  ".join(str(c).ljust(w) for c, w in zip(cells, widths)))


def print_markdown(rows):
    """Markdown table for pasting into the README."""
    print("| Target | Published Rp/R* | BLS | ΔBLS% | PINN | ΔPINN% |")
    print("|--------|-----------------|-----|-------|------|--------|")
    for r in rows:
        print(f"| {r['target']} | {_fmt(r['published'])} | "
              f"{_fmt(r['bls'])} | {_fmt(r['bls_dpct'], '{:+.1f}')} | "
              f"{_fmt(r['pinn'])} | {_fmt(r['pinn_dpct'], '{:+.1f}')} |")


def main():
    parser = argparse.ArgumentParser(
        description="Validate pipeline Rp/R* against the NASA Exoplanet Archive")
    parser.add_argument("--targets", nargs="*", default=[],
                        help="Target names, e.g. Kepler-8 Kepler-10")
    parser.add_argument("--range", nargs=3, metavar=("PREFIX", "START", "END"),
                        help="Numeric target range, e.g. --range Kepler 8 17")
    parser.add_argument("--markdown", action="store_true",
                        help="Emit a Markdown table (for the README)")
    args = parser.parse_args()

    # The table uses Δ and — ; force UTF-8 so a cp1252 Windows console
    # doesn't choke on them.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    targets = list(args.targets)
    if args.range:
        prefix, start, end = args.range
        targets += expand_range(prefix, int(start), int(end))
    if not targets:
        parser.error("Provide --targets ... or --range ...")

    rows = collect(targets)
    print() if not args.markdown else None
    (print_markdown if args.markdown else print_table)(rows)

    # A quick portfolio-friendly summary: mean absolute error per method.
    def mae(key):
        vals = [abs(r[key]) for r in rows if r[key] is not None]
        return sum(vals) / len(vals) if vals else None
    bls_mae, pinn_mae = mae("bls_dpct"), mae("pinn_dpct")
    if not args.markdown and (bls_mae is not None or pinn_mae is not None):
        print()
        print(f"Mean |Δ| vs published:  "
              f"BLS {_fmt(bls_mae, '{:.1f}')}%   "
              f"PINN {_fmt(pinn_mae, '{:.1f}')}%")


if __name__ == "__main__":
    main()
