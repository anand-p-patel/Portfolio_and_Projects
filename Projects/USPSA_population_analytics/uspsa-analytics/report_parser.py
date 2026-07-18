"""
Parser for the PractiScore "Web Report" text format (USPSA matches).

Every USPSA match results page on practiscore.com links to a plain-text
"Web Report" (https://practiscore.com/reports/web/...). It is a
comma-separated, line-prefixed format:

    $INFO key:value          match metadata (name, date, club, level, ...)
    E <comma fields>         one line per competitor (entry)
    G <comma fields>         one line per stage, incl. classifier flag + code
    I <comma fields>         one line per (stage, competitor) score,
                             including the precomputed HIT FACTOR

Field positions below follow the working open-source parser in
kmcken/CompetitionShootingAnalytics (Apache-2.0), cross-checked against
real reports. Because this is a reverse-engineered format, every line is
parsed defensively and the caller gets a ParseStats object describing
anything that was skipped, plus a hit-factor sanity check
(HF must be <= total_points / time, since penalties only subtract).

Run this module directly to parse a saved report and print a summary:

    python report_parser.py data/raw_reports/<file>.txt
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime

from config import normalize_classification, normalize_division

# E-line (competitor) field positions
E_COMP_NUM, E_MEMBER, E_FIRST, E_LAST, E_DQ = 0, 1, 2, 3, 4
E_CLASS, E_DIVISION, E_MATCH_PTS, E_PLACE, E_PF = 8, 9, 10, 11, 12

# G-line (stage) field positions
G_NUMBER, G_MIN_ROUNDS, G_MAX_PTS = 0, 2, 3
G_IS_CLASSIFIER, G_CLASSIFIER_CODE, G_NAME, G_SCORING = 4, 5, 6, 7

# I-line (stage score) field positions
I_STAGE, I_COMP, I_DQ, I_DNF = 1, 2, 3, 4
I_A, I_B, I_C, I_D, I_M, I_NS, I_PROC = 5, 6, 7, 8, 9, 10, 11
I_PENALTIES, I_TIME, I_TOTAL_PTS, I_HF, I_STAGE_PTS, I_STAGE_PLACE = 19, 25, 27, 28, 29, 30

CLASSIFIER_CODE_RE = re.compile(r"(\d{2}-\d{2})")


@dataclass
class ParseStats:
    competitors: int = 0
    stages: int = 0
    scores: int = 0
    skipped_lines: int = 0
    hf_sanity_violations: int = 0
    errors: list = field(default_factory=list)  # first few skip reasons

    def note_skip(self, reason: str):
        self.skipped_lines += 1
        if len(self.errors) < 10:
            self.errors.append(reason)


def _yes(value: str) -> bool:
    return (value or "").strip().lower() in ("yes", "true", "1")


def _to_float(value: str, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: str, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_info(lines: list[str]) -> dict:
    """$INFO lines are `key:value` pairs; keys are matched case-insensitively."""
    info = {}
    for line in lines:
        if not line.startswith("$INFO"):
            continue
        body = line[len("$INFO"):].strip()
        if ":" not in body:
            continue
        key, value = body.split(":", 1)
        info[key.strip().lower()] = value.strip()
    return info


def _parse_match_date(raw: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _match_level(raw: str) -> int | None:
    text = (raw or "").lower()
    if "iii" in text:
        return 3
    if "ii" in text:
        return 2
    if "i" in text or "1" in text:
        return 1
    return None


def _classifier_code(raw: str) -> str | None:
    """Pull a `NN-NN` code out of whatever the report put in that field."""
    m = CLASSIFIER_CODE_RE.search(raw or "")
    return m.group(1) if m else ((raw or "").strip().upper() or None)


def parse_report(text: str) -> tuple[dict, ParseStats]:
    """
    Parse one web-report file.

    Returns (parsed, stats) where parsed = {
        "match":       {name, match_date, club_name, club_code, level},
        "stages":      [ {number, name, min_rounds, max_points,
                          is_classifier, classifier_code, scoring} ],
        "competitors": [ {comp_number, member_number, first_name, last_name,
                          division_raw, division, classification,
                          power_factor, dq, match_points, place} ],
        "scores":      [ {stage_number, comp_number, a..ns, procedurals,
                          penalties, time, total_points, hit_factor,
                          stage_points, stage_place, dq, dnf} ],
    }
    """
    lines = text.splitlines()
    stats = ParseStats()

    info = _parse_info(lines)
    if "match name" not in info:
        raise ValueError("Not a PractiScore web report: no `$INFO Match name` line found.")

    match = {
        "name": info.get("match name", "Unknown match"),
        "match_date": _parse_match_date(info.get("match date", "")),
        "club_name": info.get("club name") or None,
        "club_code": info.get("club code") or None,
        "level": _match_level(info.get("match level", "")),
    }

    stages, competitors, scores = [], [], []

    for raw_line in lines:
        try:
            if raw_line.startswith("E "):
                f = raw_line[2:].rstrip("\n").split(",")
                if len(f) <= E_PF:
                    stats.note_skip(f"E line too short ({len(f)} fields)")
                    continue
                competitors.append({
                    "comp_number": _to_int(f[E_COMP_NUM]),
                    "member_number": f[E_MEMBER].strip() or None,
                    "first_name": f[E_FIRST].strip(),
                    "last_name": f[E_LAST].strip(),
                    "dq": _yes(f[E_DQ]),
                    "classification": normalize_classification(f[E_CLASS]),
                    "division_raw": f[E_DIVISION].strip(),
                    "division": normalize_division(f[E_DIVISION]),
                    "match_points": _to_float(f[E_MATCH_PTS], 0.0),
                    "place": _to_int(f[E_PLACE]),
                    "power_factor": f[E_PF].strip() or None,
                })
                stats.competitors += 1

            elif raw_line.startswith("G "):
                f = raw_line[2:].rstrip("\n").split(",")
                if len(f) <= G_SCORING:
                    stats.note_skip(f"G line too short ({len(f)} fields)")
                    continue
                is_classifier = _yes(f[G_IS_CLASSIFIER])
                stages.append({
                    "number": _to_int(f[G_NUMBER]),
                    "min_rounds": _to_int(f[G_MIN_ROUNDS]),
                    "max_points": _to_int(f[G_MAX_PTS]),
                    "is_classifier": is_classifier,
                    "classifier_code": _classifier_code(f[G_CLASSIFIER_CODE]) if is_classifier else None,
                    "name": f[G_NAME].strip(),
                    "scoring": f[G_SCORING].strip(),
                })
                stats.stages += 1

            elif raw_line.startswith("I "):
                f = raw_line[2:].rstrip("\n").split(",")
                if len(f) <= I_STAGE_PLACE:
                    stats.note_skip(f"I line too short ({len(f)} fields)")
                    continue
                hf = _to_float(f[I_HF])
                time_s = _to_float(f[I_TIME])
                total_pts = _to_int(f[I_TOTAL_PTS])
                # Sanity: HF = (points - penalty points) / time, so it can
                # never exceed points/time. Flag violations instead of
                # silently trusting a possibly shifted column.
                if hf is not None and time_s and time_s > 0 and total_pts:
                    if hf > (total_pts / time_s) + 0.01:
                        stats.hf_sanity_violations += 1
                scores.append({
                    "stage_number": _to_int(f[I_STAGE]),
                    "comp_number": _to_int(f[I_COMP]),
                    "dq": _yes(f[I_DQ]),
                    "dnf": _yes(f[I_DNF]),
                    "a": _to_int(f[I_A], 0), "b": _to_int(f[I_B], 0),
                    "c": _to_int(f[I_C], 0), "d": _to_int(f[I_D], 0),
                    "m": _to_int(f[I_M], 0), "ns": _to_int(f[I_NS], 0),
                    "procedurals": _to_int(f[I_PROC], 0),
                    "penalties": _to_int(f[I_PENALTIES], 0),
                    "time": time_s,
                    "total_points": total_pts,
                    "hit_factor": hf,
                    "stage_points": _to_float(f[I_STAGE_PTS]),
                    "stage_place": _to_int(f[I_STAGE_PLACE]),
                })
                stats.scores += 1

        except Exception as exc:  # never let one bad line kill a match
            stats.note_skip(f"{raw_line[:40]!r}: {exc}")

    parsed = {"match": match, "stages": stages,
              "competitors": competitors, "scores": scores}
    return parsed, stats


def looks_like_web_report(text: str) -> bool:
    head = text[:4000]
    return "$INFO" in head and "Match name" in head.replace("match", "Match")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python report_parser.py <path-to-web-report.txt>")
    content = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    parsed, stats = parse_report(content)
    m = parsed["match"]
    print(f"Match: {m['name']} | {m['match_date']} | {m['club_name']} (L{m['level']})")
    print(f"Competitors: {stats.competitors}  Stages: {stats.stages}  Scores: {stats.scores}")
    classifiers = [s for s in parsed["stages"] if s["is_classifier"]]
    print(f"Classifier stages: {[(s['number'], s['classifier_code']) for s in classifiers]}")
    print(f"Skipped lines: {stats.skipped_lines}  HF sanity violations: {stats.hf_sanity_violations}")
    if stats.errors:
        print("First skip reasons:", *stats.errors, sep="\n  ")
