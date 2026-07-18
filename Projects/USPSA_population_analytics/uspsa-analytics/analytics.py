"""
Metrics layer: pandas over the SQL schema.

Two analyses, matching the project brief:

1. Division participation over time
   Registrations per period per division (counts and share).

2. Classifier difficulty vs classification
   For each classifier stage code, pool every valid hit factor and group by
   USPSA classification (GM..U). Raw mean HF confounds two things: how good
   the shooters are and how hard the stage is. To isolate the stage, each
   classification's mean HFs are z-scored *across classifiers within that
   class* — removing the class's skill offset — and the per-class z-scores
   are then averaged per classifier:

        z[c, k]      = (meanHF[c, k] - mu_k) / sigma_k        (within class k)
        difficulty_c = -mean_k( z[c, k] )

   A positive difficulty score means every class, from GM to D, shot that
   classifier below their own typical level: the stage itself is hard.
   Minimum-sample thresholds keep noise out of the cells.
"""

from __future__ import annotations

import pandas as pd

from config import (CLASS_ORDER, CLASSIFIER_TITLES_CSV, FOCUS_DIVISIONS)

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def registrations_frame(engine) -> pd.DataFrame:
    """One row per (match, competitor): the participation fact table."""
    q = """
        SELECT c.id AS competitor_id, c.division, c.classification, c.dq,
               c.member_number, m.id AS match_id, m.name AS match_name,
               m.match_date, m.club_name, m.level
        FROM competitors c
        JOIN matches m ON m.id = c.match_id
        WHERE m.match_date IS NOT NULL
    """
    df = pd.read_sql(q, engine, parse_dates=["match_date"])
    df["classification"] = pd.Categorical(df["classification"],
                                          categories=CLASS_ORDER, ordered=True)
    return df


def classifier_scores_frame(engine) -> pd.DataFrame:
    """One row per valid hit factor on a classifier stage."""
    q = """
        SELECT ss.hit_factor, ss.time, ss.total_points,
               s.classifier_code, s.name AS stage_name,
               c.division, c.classification, c.dq AS match_dq,
               ss.dq AS stage_dq, ss.dnf,
               m.id AS match_id, m.match_date, m.name AS match_name
        FROM stage_scores ss
        JOIN stages s      ON s.id = ss.stage_id
        JOIN competitors c ON c.id = ss.competitor_id
        JOIN matches m     ON m.id = ss.match_id
        WHERE s.is_classifier
          AND s.classifier_code IS NOT NULL
          AND ss.hit_factor IS NOT NULL
    """
    df = pd.read_sql(q, engine, parse_dates=["match_date"])
    # Zero HFs are DNFs/DQs/no-shoots in disguise; they measure attendance,
    # not stage difficulty.
    for col in ("stage_dq", "dnf", "match_dq"):
        df[col] = df[col].fillna(False).astype(bool)
    df = df[(df["hit_factor"] > 0)
            & ~df["stage_dq"] & ~df["dnf"] & ~df["match_dq"]].copy()
    df["classification"] = pd.Categorical(df["classification"],
                                          categories=CLASS_ORDER, ordered=True)
    return df


def classifier_titles() -> pd.DataFrame:
    """code -> official classifier title (bundled reference CSV)."""
    try:
        t = pd.read_csv(CLASSIFIER_TITLES_CSV)
        t["code"] = t["code"].astype(str).str.strip()
        return t
    except FileNotFoundError:
        return pd.DataFrame(columns=["code", "title"])


def label_codes(codes: pd.Series) -> pd.Series:
    titles = classifier_titles().set_index("code")["title"]
    return codes.map(lambda c: f"{c} · {titles[c]}" if c in titles.index else str(c))


# ---------------------------------------------------------------------------
# 1) Division trends
# ---------------------------------------------------------------------------
def division_trend(reg: pd.DataFrame,
                   divisions: list[str] | None = None,
                   freq: str = "MS",
                   include_dq: bool = True) -> pd.DataFrame:
    """
    Long-format trend table: period | division | shooters | share.

    `share` is each division's fraction of ALL registrations that period
    (denominator includes divisions outside the selected set, so the four
    focus divisions can be compared against the whole field).
    """
    divisions = divisions or FOCUS_DIVISIONS
    df = reg if include_dq else reg[~reg["dq"].astype(bool)]
    if df.empty:
        return pd.DataFrame(columns=["period", "division", "shooters", "share"])

    df = df.assign(period=df["match_date"].dt.to_period(
        {"MS": "M", "QS": "Q", "W": "W"}.get(freq, "M")).dt.start_time)

    totals = df.groupby("period").size().rename("total")
    counts = (df[df["division"].isin(divisions)]
              .groupby(["period", "division"]).size().rename("shooters")
              .reset_index())
    counts = counts.merge(totals, on="period")
    counts["share"] = counts["shooters"] / counts["total"]
    return counts.sort_values(["period", "division"]).reset_index(drop=True)


def matches_per_period(reg: pd.DataFrame, freq: str = "MS") -> pd.DataFrame:
    if reg.empty:
        return pd.DataFrame(columns=["period", "matches"])
    df = reg.assign(period=reg["match_date"].dt.to_period(
        {"MS": "M", "QS": "Q", "W": "W"}.get(freq, "M")).dt.start_time)
    return (df.groupby("period")["match_id"].nunique()
              .rename("matches").reset_index())


# ---------------------------------------------------------------------------
# 2) Classifier difficulty
# ---------------------------------------------------------------------------
def class_by_classifier(scores: pd.DataFrame, min_n: int = 5) -> pd.DataFrame:
    """
    Cell table: classifier_code x classification with n / mean / median HF.
    Cells with fewer than `min_n` runs are dropped (too noisy to trust).
    """
    if scores.empty:
        return pd.DataFrame(columns=["classifier_code", "classification",
                                     "n", "mean_hf", "median_hf"])
    g = (scores.groupby(["classifier_code", "classification"], observed=True)
               ["hit_factor"]
               .agg(n="count", mean_hf="mean", median_hf="median")
               .reset_index())
    return g[g["n"] >= min_n].reset_index(drop=True)


def difficulty_scores(cells: pd.DataFrame, min_classes: int = 3) -> pd.DataFrame:
    """
    Z-score each class's mean HFs across classifiers, then average the
    (negated) z-scores per classifier. Requires each classifier to have
    >= min_classes populated class cells, and each class column to span
    >= 2 classifiers (otherwise sigma is undefined).
    """
    if cells.empty:
        return pd.DataFrame(columns=["classifier_code", "difficulty",
                                     "classes_used", "total_runs", "overall_mean_hf"])

    wide = cells.pivot(index="classifier_code", columns="classification",
                       values="mean_hf")
    # Drop class columns that only appear on one classifier (sigma undefined).
    wide = wide.loc[:, wide.notna().sum() >= 2]

    z = (wide - wide.mean()) / wide.std(ddof=1)
    z = z.dropna(axis=1, how="all")

    enough = z.notna().sum(axis=1) >= min_classes
    z = z[enough]
    if z.empty:
        return pd.DataFrame(columns=["classifier_code", "difficulty",
                                     "classes_used", "total_runs", "overall_mean_hf"])

    runs = cells.groupby("classifier_code")["n"].sum()
    sums = (cells.assign(w=cells["mean_hf"] * cells["n"])
                 .groupby("classifier_code")[["w", "n"]].sum())
    overall = sums["w"] / sums["n"]  # run-weighted mean HF per classifier

    out = pd.DataFrame({
        "classifier_code": z.index,
        "difficulty": -z.mean(axis=1).values,        # higher = harder
        "classes_used": z.notna().sum(axis=1).values,
        "total_runs": runs.reindex(z.index).values,
        "overall_mean_hf": overall.reindex(z.index).values,
    }).sort_values("difficulty", ascending=False).reset_index(drop=True)
    return out


def hf_heatmap_table(cells: pd.DataFrame, order_by: pd.DataFrame | None = None) -> pd.DataFrame:
    """Wide mean-HF table (rows = classifier, cols = class), hardest first."""
    if cells.empty:
        return pd.DataFrame()
    wide = cells.pivot(index="classifier_code", columns="classification",
                       values="mean_hf")
    wide = wide.reindex(columns=[c for c in CLASS_ORDER if c in wide.columns])
    if order_by is not None and not order_by.empty:
        ranked = [c for c in order_by["classifier_code"] if c in wide.index]
        rest = [c for c in wide.index if c not in ranked]
        wide = wide.reindex(ranked + rest)
    return wide


if __name__ == "__main__":
    from db import get_engine
    eng = get_engine()
    reg = registrations_frame(eng)
    scr = classifier_scores_frame(eng)
    print(f"registrations: {len(reg):,} | classifier runs: {len(scr):,}")
    trend = division_trend(reg)
    print(trend.tail(8).to_string(index=False))
    cells = class_by_classifier(scr)
    diff = difficulty_scores(cells)
    print(diff.head(10).to_string(index=False))
