"""
Parser for the JSON data embedded in a PractiScore *public* results page.

Why this exists (see docs/superpowers/specs/2026-07-19-embedded-json-
ingestion-design.md): the login-gated "Web Report" text file is not the
only source of a match's data. Every public results page
(practiscore.com/results/new/<id>) server-renders the COMPLETE dataset
into three inline JavaScript variables — no login, no S3 fetch:

    matchDef = {...}   # name, date, club, level, shooters, stage defs
    scores   = {...}   # raw per-stage strings/hits (not needed here)
    results  = [...]   # PractiScore's OWN precomputed standings:
                       #   results[0]       -> match-level rows
                       #   results[i>=1]    -> stage i rows (A/C/D/M/NS,
                       #                       Time, HF, stage pts, place)

`scrape.py` reads those variables straight out of the rendered page
(the browser has already JSON-parsed them) and hands us the dict. We
turn it into the EXACT same `parsed` structure `report_parser.parse_report`
returns, so db.py / analytics.py / dashboard.py never know the
difference. `report_parser.py` is left untouched.

Two facts make this reliable and keep it honest:
  * Scoring values are read from matchDef.match_pfs (the match's own
    power-factor table), never hardcoded.
  * The per-stage `details` block gives A/C/D/M/NS/Time/HF but NOT
    procedurals. So net points AND procedurals are reconciled from the
    hit counts, and any row where that reconciliation fails becomes an
    hf_sanity_violation — the same tripwire report_parser uses.

Run directly to parse a saved page-data JSON and print a summary:

    python embedded_parser.py data/raw_reports/<file>.json
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime

from config import normalize_classification, normalize_division
# Reuse the ParseStats + a couple of tiny coercers from the text parser so
# both ingest paths report progress and failures identically.
from report_parser import ParseStats, _to_float, _to_int, _match_level

# Rounding slack when reconciling hit points against HF*time. HF is stored
# to 4 decimals, time to 2, so the product carries a little noise.
_HF_POINTS_TOL = 0.75

# PractiScore's match_subtype / match_type -> the region label the text
# Web Report would put in `$INFO Region`. USPSA-app matches run under IPSC
# or Steel rules carry those subtypes; that is what the default filter
# keys on, so we surface it the same way.
_REGION_BY_SUBTYPE = {
    "uspsa": "USPSA", "ipsc": "IPSC", "sc": "SCSA", "scsa": "SCSA",
    "steel": "SCSA", "idpa": "IDPA",
}


def _region(match_def: dict) -> str | None:
    sub = (match_def.get("match_subtype") or "").strip().lower()
    if sub in _REGION_BY_SUBTYPE:
        return _REGION_BY_SUBTYPE[sub]
    mtype = (match_def.get("match_type") or "").strip().lower()
    if mtype.startswith("uspsa"):
        return "USPSA"
    if mtype.startswith("sc"):
        return "SCSA"
    return sub.upper() or None


def _parse_iso_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:len(fmt) + 4], fmt).date()
        except (ValueError, TypeError):
            continue
    # Last resort: leading YYYY-MM-DD of a longer timestamp.
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _pf_tables(match_def: dict) -> dict[str, dict]:
    """name(lower) -> {A,B,C,D,M,NS} point values from match_pfs."""
    out: dict[str, dict] = {}
    for pf in match_def.get("match_pfs") or []:
        name = (pf.get("name") or "").strip().lower()
        if not name:
            continue
        out[name] = {k: _to_int(pf.get(k), 0) for k in
                     ("A", "B", "C", "D", "M", "NS")}
    # Fallback if a match somehow ships no table (USPSA canonical values).
    out.setdefault("major", {"A": 5, "B": 4, "C": 4, "D": 2, "M": 10, "NS": 10})
    out.setdefault("minor", {"A": 5, "B": 3, "C": 3, "D": 1, "M": 10, "NS": 10})
    return out


def _int_detail(details: dict, key: str) -> int:
    return _to_int(details.get(key), 0) or 0


def parse_embedded(data: dict) -> tuple[dict, ParseStats]:
    """
    Parse one public-results-page payload.

    `data` is {"matchDef": {...}, "scores": {...}, "results": [...]}
    (the three page variables) optionally plus a "meta" block, exactly
    as scrape.py saves it.

    Returns (parsed, stats) with the SAME shape report_parser.parse_report
    produces — see that function's docstring for the field contract.
    """
    match_def = data.get("matchDef") or {}
    results = data.get("results") or []
    if not match_def:
        raise ValueError("Not a PractiScore results payload: no matchDef.")

    stats = ParseStats()

    match = {
        "name": match_def.get("match_name") or "Unknown match",
        "match_date": _parse_iso_date(match_def.get("match_date", "")),
        "club_name": (match_def.get("match_clubname") or "").strip() or None,
        "club_code": (match_def.get("match_clubcode")
                      or match_def.get("psclubcode") or "").strip() or None,
        "level": _match_level(str(match_def.get("match_level", ""))),
        "region": _region(match_def),
    }

    pf_tables = _pf_tables(match_def)

    # ---- Stages -----------------------------------------------------------
    # match_stages is ordered; the k-th entry's scores live in results[k].
    # We number stages by that 1-based POSITION, not by sd["stage_number"]:
    # a two-in-one match reuses display numbers (1,2,3,4,1,2,3,4) which both
    # collides on the DB's (match_id, number) key and mismatches how score
    # rows reference their stage (by results-array index). Position keeps
    # numbers unique and aligned with the scores below.
    stages = []
    stage_defs = match_def.get("match_stages") or []
    for pos, sd in enumerate(stage_defs, start=1):
        is_classifier = bool(sd.get("stage_classifier"))
        code = (sd.get("stage_classifiercode") or "").strip().upper() or None
        stages.append({
            "number": pos,
            "name": (sd.get("stage_name") or "").strip(),
            "min_rounds": _to_int(sd.get("stage_minrounds")),
            "max_points": _to_int(sd.get("stage_tppoints")),
            "is_classifier": is_classifier,
            "classifier_code": code if is_classifier else None,
            "scoring": (sd.get("stage_scoretype") or "").strip() or None,
        })
        stats.stages += 1

    # ---- Competitors ------------------------------------------------------
    # Build from match_shooters; assign a stable 1-based comp_number and a
    # sh_uid -> comp_number map so score rows (keyed by shooterId) can join.
    shooters = [s for s in (match_def.get("match_shooters") or [])
                if not s.get("sh_del")]
    comp_by_uid: dict[str, int] = {}
    pf_by_uid: dict[str, str] = {}
    competitors = []
    for i, sh in enumerate(shooters, start=1):
        uid = sh.get("sh_uid") or sh.get("sh_uuid")
        comp_by_uid[uid] = i
        pf = (sh.get("sh_pf") or "").strip()
        pf_by_uid[uid] = pf
        member = sh.get("sh_id") or sh.get("sh_num")
        member = str(member).strip() if member not in (None, "", -1, "-1") else None
        div_raw = (sh.get("sh_dvp") or "").strip()
        competitors.append({
            "comp_number": i,
            "member_number": member,
            "first_name": (sh.get("sh_fn") or "").strip(),
            "last_name": (sh.get("sh_ln") or "").strip(),
            "dq": bool(sh.get("sh_dq")),
            "classification": normalize_classification(sh.get("sh_grd")),
            "division_raw": div_raw,
            "division": normalize_division(div_raw),
            "match_points": 0.0,   # filled from results[0] below
            "place": None,
            "power_factor": pf or None,
        })
        stats.competitors += 1

    comp_by_number = {c["comp_number"]: c for c in competitors}

    # ---- Match-level standings (results[0]) -> competitor points/place ----
    if results:
        for row in results[0]:
            cn = comp_by_uid.get(row.get("shooterId"))
            if cn is None:
                continue
            comp = comp_by_number[cn]
            comp["match_points"] = _to_float(row.get("result"), 0.0)
            comp["place"] = _to_int(row.get("rank"))

    # ---- Per-stage scores (results[1..]) ----------------------------------
    scores = []
    for stage_idx in range(1, len(results)):
        stage_number = stage_idx  # results index is the stage number
        for row in results[stage_idx]:
            uid = row.get("shooterId")
            cn = comp_by_uid.get(uid)
            if cn is None:
                stats.note_skip(f"score for unknown shooter {uid}")
                continue
            d = row.get("details") or {}
            a = _int_detail(d, "A")
            b = _int_detail(d, "B")
            c = _int_detail(d, "C")
            dd = _int_detail(d, "D")
            m = _int_detail(d, "M")
            ns = _int_detail(d, "NS")
            time_s = _to_float(d.get("Time"))
            hf = _to_float(d.get("HF"))

            pf_name = (pf_by_uid.get(uid) or "minor").lower()
            pv = pf_tables.get(pf_name) or pf_tables["minor"]

            net_points = None
            procedurals = 0
            penalties = 0
            if hf is not None and time_s and time_s > 0:
                net_points = int(round(hf * time_s))
                # Reconcile only scored rows. A zeroed HF (hf==0, so
                # net_points==0) is a floored/DQ/no-score stage — the raw
                # score went <=0 from misses/penalties — not a mapping
                # error. report_parser skips its own HF check the same way
                # (it requires total_pts truthy).
                if net_points:
                    gross = (a * pv["A"] + b * pv["B"] + c * pv["C"]
                             + dd * pv["D"] - m * pv["M"] - ns * pv["NS"])
                    implied = gross - net_points
                    # implied should be a non-negative multiple of 10 (each
                    # procedural = -10). Anything else means the hit counts
                    # or the major/minor table don't match this row's HF.
                    if implied < -_HF_POINTS_TOL or abs(
                            implied - round(implied / 10.0) * 10) > _HF_POINTS_TOL:
                        stats.hf_sanity_violations += 1
                    else:
                        procedurals = max(0, int(round(implied / 10.0)))
                        penalties = procedurals * 10

            dnf = (not time_s) and (not net_points) and (not hf)
            scores.append({
                "stage_number": stage_number,
                "comp_number": cn,
                "dq": bool(comp_by_number[cn]["dq"]) and net_points in (None, 0),
                "dnf": dnf,
                "a": a, "b": b, "c": c, "d": dd, "m": m, "ns": ns,
                "procedurals": procedurals,
                "penalties": penalties,
                "time": time_s,
                "total_points": net_points,
                "hit_factor": hf,
                "stage_points": _to_float(row.get("result")),
                "stage_place": _to_int(row.get("rank")),
            })
            stats.scores += 1

    parsed = {"match": match, "stages": stages,
              "competitors": competitors, "scores": scores}
    return parsed, stats


def looks_like_results_payload(data: dict) -> bool:
    """True if `data` holds a populated embedded matchDef (an object with
    match_shooters) — the guard that rejects old pages' empty JS stubs."""
    return bool(isinstance(data, dict) and data.get("matchDef")
               and (data.get("matchDef") or {}).get("match_shooters") is not None)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python embedded_parser.py <path-to-page-data.json>")
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    parsed, stats = parse_embedded(payload)
    mm = parsed["match"]
    print(f"Match: {mm['name']} | {mm['match_date']} | {mm['club_name']} "
          f"(L{mm['level']}) | region={mm['region']}")
    print(f"Competitors: {stats.competitors}  Stages: {stats.stages}  "
          f"Scores: {stats.scores}")
    classifiers = [s for s in parsed["stages"] if s["is_classifier"]]
    print(f"Classifier stages: "
          f"{[(s['number'], s['classifier_code']) for s in classifiers]}")
    print(f"Skipped: {stats.skipped_lines}  "
          f"HF sanity violations: {stats.hf_sanity_violations}")
    if stats.errors:
        print("First skip reasons:", *stats.errors, sep="\n  ")
