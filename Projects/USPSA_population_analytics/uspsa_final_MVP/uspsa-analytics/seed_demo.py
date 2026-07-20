"""
Synthetic USPSA season generator — demo mode.

Builds ~18 months of realistic-shaped match data and pushes it through the
SAME ingestion path as real scrapes (db.upsert_match), so it exercises the
schema end-to-end and gives the dashboard something to show before you've
scraped anything.

What it simulates (all clearly synthetic — do not present as real data):
  * Division popularity drifting over time (Limited Optics rising,
    Limited/Open sliding — the shape of the real-world story, invented numbers)
  * A classification pyramid (lots of C/B, few M/GM, a U tail)
  * One classifier stage per match drawn from real classifier codes, each
    with a latent difficulty scale + a "punishes lower classes" exponent,
    so the Z-score analysis has real structure to recover
  * Internally consistent scores: HF == (points - penalty points) / time

Usage:
    python seed_demo.py                 # ~120 matches
    python seed_demo.py --matches 60 --reset
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

# -- wrong-folder guard -----------------------------------------------------
# If Python resolves `config` to another project's config.py (two codebases
# sharing one folder), stop before importing anything else.
import config as _cfg
if getattr(_cfg, "PROJECT_TAG", None) != "uspsa-analytics":
    import sys as _sys
    _sys.exit(
        "\nSTOP: the config.py in this folder belongs to a different project,\n"
        "so this USPSA script would run against the wrong code.\n"
        "Extract uspsa-analytics.zip into its OWN folder and run from there.\n"
        "(`python check_setup.py` diagnoses folder problems.)")
# ---------------------------------------------------------------------------

import db
from config import CLASSIFIER_TITLES_CSV

RNG = np.random.default_rng(20260718)

CLUBS = [
    ("Bayou City Practical", "TX01"), ("Hill Country Action", "TX02"),
    ("Gulf Coast USPSA", "TX03"), ("Piney Woods Pistol", "TX04"),
    ("Brazos Valley Blasters", "TX05"), ("Lone Star Steel & Paper", "TX06"),
]

# Classification pyramid and skill (relative pace; GM = 1.0)
CLASS_P = {"GM": .02, "M": .05, "A": .13, "B": .24, "C": .30, "D": .10, "U": .16}
CLASS_SKILL = {"GM": 1.00, "M": .90, "A": .80, "B": .69, "C": .575, "D": .46, "U": .58}
CLASS_SIGMA = {"U": .25}  # unclassified shooters are all over the map
DEFAULT_SIGMA = .13

# Division mix at the start vs the end of the window (linearly interpolated)
DIV_START = {"Carry Optics": .30, "Limited": .21, "Open": .12, "Limited Optics": .05,
             "PCC": .13, "Production": .11, "Single Stack": .05, "Revolver": .03}
DIV_END = {"Carry Optics": .30, "Limited": .11, "Open": .09, "Limited Optics": .22,
           "PCC": .13, "Production": .08, "Single Stack": .04, "Revolver": .03}

N_CLASSIFIERS = 14  # distinct classifier codes in circulation


def _pick_classifiers() -> pd.DataFrame:
    """Sample real codes/titles; attach latent difficulty parameters."""
    titles = pd.read_csv(CLASSIFIER_TITLES_CSV)
    picks = titles.sample(N_CLASSIFIERS, random_state=7).reset_index(drop=True)
    # GM-pace hit factor for the stage (lower = harder), and gamma:
    # gamma > 1 widens the class gap (technical stages punish D/C harder).
    picks["gm_hf"] = RNG.uniform(4.2, 9.8, len(picks)).round(2)
    picks["gamma"] = RNG.uniform(0.90, 1.30, len(picks)).round(2)
    return picks


def _division_weights(t: float) -> tuple[list[str], np.ndarray]:
    divs = list(DIV_START)
    w = np.array([(1 - t) * DIV_START[d] + t * DIV_END[d] for d in divs])
    return divs, w / w.sum()


def _shooter_pool(n_total: int) -> pd.DataFrame:
    """A persistent local population; matches sample from it."""
    classes = RNG.choice(list(CLASS_P), size=n_total, p=list(CLASS_P.values()))
    skill_noise = np.array([
        RNG.lognormal(0, CLASS_SIGMA.get(c, DEFAULT_SIGMA) * 0.6) for c in classes
    ])
    first = [f"Shooter{i:04d}" for i in range(n_total)]
    member = [f"A{RNG.integers(10_000, 999_999)}" for _ in range(n_total)]
    return pd.DataFrame({
        "first_name": first, "last_name": "Demo",
        "member_number": member, "classification": classes,
        "ability": skill_noise,  # persistent within-class talent
    })


def build_match(match_i: int, day: date, t: float, pool: pd.DataFrame,
                classifiers: pd.DataFrame) -> dict:
    club_name, club_code = CLUBS[match_i % len(CLUBS)]
    n_shooters = int(RNG.integers(30, 72))
    shooters = pool.sample(n_shooters).reset_index(drop=True)

    divs, w = _division_weights(t)
    shooters["division"] = RNG.choice(divs, size=n_shooters, p=w)
    shooters["dq"] = RNG.random(n_shooters) < 0.015

    # Stages: 4 field courses + 1 classifier
    n_field = int(RNG.integers(4, 6))
    stage_rows, cl = [], classifiers.sample(1).iloc[0]
    for num in range(1, n_field + 1):
        rounds = int(RNG.integers(16, 33))
        stage_rows.append({"number": num, "name": f"Stage {num}",
                           "min_rounds": rounds, "max_points": rounds * 5,
                           "is_classifier": False, "classifier_code": None,
                           "scoring": "Comstock",
                           "_scale": RNG.uniform(4.6, 8.2), "_gamma": 1.0})
    cl_rounds = int(RNG.integers(12, 25))
    stage_rows.append({"number": n_field + 1, "name": f"CM {cl['code']} {cl['title']}",
                       "min_rounds": cl_rounds, "max_points": cl_rounds * 5,
                       "is_classifier": True, "classifier_code": cl["code"],
                       "scoring": "Comstock",
                       "_scale": float(cl["gm_hf"]), "_gamma": float(cl["gamma"])})

    competitors, scores = [], []
    for comp_number, sh in enumerate(shooters.itertuples(index=False), start=1):
        competitors.append({
            "comp_number": comp_number, "member_number": sh.member_number,
            "first_name": sh.first_name, "last_name": sh.last_name,
            "division_raw": sh.division, "division": sh.division,
            "classification": sh.classification, "power_factor": "Minor",
            "dq": bool(sh.dq), "match_points": None, "place": None,
        })
        if sh.dq:
            continue
        base = CLASS_SKILL[sh.classification] * sh.ability
        for st in stage_rows:
            hf = (base ** st["_gamma"]) * st["_scale"] * RNG.lognormal(0, 0.15)
            hf = max(hf, 0.15)
            rounds = st["min_rounds"]
            acc = float(np.clip(RNG.normal(0.80 + 0.15 * base, 0.06), 0.45, 0.97))
            a = int(round(rounds * acc))
            m = int(RNG.random() < 0.12) + int(RNG.random() < 0.04)
            m = min(m, rounds - a) if rounds > a else 0
            c_hits = max(rounds - a - m, 0)
            points = 5 * a + 3 * c_hits           # minor scoring
            pen_pts = 10 * m
            if points - pen_pts <= 0:
                points, pen_pts, hf = 5 * max(a, 1), 0, min(hf, 2.0)
            time_s = round((points - pen_pts) / hf, 2)
            scores.append({
                "stage_number": st["number"], "comp_number": comp_number,
                "dq": False, "dnf": False,
                "a": a, "b": 0, "c": c_hits, "d": 0, "m": m, "ns": 0,
                "procedurals": 0, "penalties": m,
                "time": time_s, "total_points": points,
                "hit_factor": round(hf, 4),
                "stage_points": None, "stage_place": None,
            })

    stages = [{k: v for k, v in s.items() if not k.startswith("_")}
              for s in stage_rows]
    return {
        "match": {"name": f"{club_name} USPSA #{match_i + 1}",
                  "match_date": day, "club_name": club_name,
                  "club_code": club_code, "level": 1},
        "stages": stages, "competitors": competitors, "scores": scores,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matches", type=int, default=120)
    ap.add_argument("--months", type=int, default=18)
    ap.add_argument("--reset", action="store_true",
                    help="drop and recreate all tables first")
    args = ap.parse_args()

    engine = db.get_engine()
    if args.reset:
        db.Base.metadata.drop_all(engine)
    db.init_db(engine)

    end = date.today()
    start = end - timedelta(days=int(args.months * 30.4))
    span = (end - start).days
    days = sorted(start + timedelta(days=int(x))
                  for x in RNG.uniform(0, span, args.matches))

    pool = _shooter_pool(900)
    classifiers = _pick_classifiers()
    print(f"Seeding {args.matches} synthetic matches "
          f"({start} → {end}) into {engine.url} ...")

    with Session(engine) as session:
        for i, day in enumerate(days):
            t = (day - start).days / span
            parsed = build_match(i, day, t, pool, classifiers)
            db.upsert_match(session, parsed, source_key=f"demo-{i:04d}")
            if (i + 1) % 20 == 0:
                session.commit()
                print(f"  {i + 1}/{args.matches} matches...")
        session.commit()

    print("\nDone.", db.summary(engine))
    print("\nNext:  streamlit run dashboard.py")


if __name__ == "__main__":
    main()
