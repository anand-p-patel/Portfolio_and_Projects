"""
PHASE 4 — PRESENTATION. Streamlit dashboard (end-user UI).

    streamlit run dashboard.py

Design notes: dark "shot-timer" theme (see .streamlit/config.toml) — slate
background, brass-amber readouts in monospace like a timer display, and a
GM→U classification ribbon as the header mark. Charts drop legends in favor
of end-of-line division tags, and an insight strip answers the two headline
questions (who's growing, what's hardest) in plain language before any
chart is read.

Populate the database first with either:
    python seed_demo.py        # synthetic season, instant demo
    python scrape.py           # real PractiScore data you harvested
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

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
from analytics import (
    class_by_classifier, classifier_scores_frame, difficulty_scores,
    division_trend, hf_heatmap_table, label_codes, matches_per_period,
    registrations_frame,
)
from fetch_panel import render_fetch_panel
from config import (
    CLASS_COLORS, CLASS_ORDER, DIVISION_COLORS,
    DIVISION_SHORT, FOCUS_DIVISIONS,
)

st.set_page_config(page_title="USPSA Population Analytics",
                   page_icon="🎯", layout="wide")

FREQ = {"Day": "D", "Week": "W", "Month": "MS", "Quarter": "QS"}


def default_gran(span_days: int) -> str:
    """Pick a sensible granularity for the range so a narrow fetch still
    shows multiple points (a line needs ≥2) instead of one collapsed dot."""
    if span_days > 730:
        return "Quarter"
    if span_days > 120:
        return "Month"
    if span_days > 21:
        return "Week"
    return "Day"


GRID = "rgba(148,163,184,.14)"
INK = "#cbd5e1"
AMBER = "#f59e0b"

# ---------------------------------------------------------------------------
# Look & feel
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

h1, h2, h3, [data-testid="stSidebar"] h2 {
  font-family: 'Barlow Condensed', sans-serif !important;
  text-transform: uppercase; letter-spacing: .06em;
}
h1 { font-size: 2.6rem !important; margin-bottom: 0 !important; }
.block-container { padding-top: 2.4rem; max-width: 1300px; }

/* GM→U classification ribbon: the header mark */
.ribbon { display:flex; height:6px; border-radius:3px; overflow:hidden;
          margin:.55rem 0 1.1rem 0; }
.ribbon span { flex:1; }

/* Timer-style readout cards */
.kpi { background:#141a22; border:1px solid rgba(148,163,184,.18);
       border-radius:10px; padding:.85rem 1rem .7rem; }
.kpi .lbl { font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
            color:#94a3b8; }
.kpi .val { font-family:'IBM Plex Mono', monospace; font-weight:600;
            font-size:1.9rem; color:#f59e0b; line-height:1.15;
            font-variant-numeric: tabular-nums; }
.kpi .sub { font-size:.74rem; color:#64748b; }

/* Plain-language insight cards */
.insight { background:#141a22; border-left:3px solid #f59e0b;
           border-radius:8px; padding:.7rem .95rem; height:100%; }
.insight .tag { font-size:.7rem; letter-spacing:.14em; text-transform:uppercase;
                color:#94a3b8; }
.insight .txt { font-size:.95rem; color:#e2e8f0; margin-top:.15rem; }
.insight b { color:#f59e0b; }

[data-testid="stCaptionContainer"] { color:#94a3b8; }
</style>
""", unsafe_allow_html=True)


def ribbon_html() -> str:
    segs = "".join(f"<span style='background:{CLASS_COLORS[c]}'></span>"
                   for c in CLASS_ORDER)
    return f"<div class='ribbon'>{segs}</div>"


def kpi(col, label: str, value: str, sub: str = "") -> None:
    col.markdown(f"<div class='kpi'><div class='lbl'>{label}</div>"
                 f"<div class='val'>{value}</div>"
                 f"<div class='sub'>{sub}</div></div>", unsafe_allow_html=True)


def insight(col, tag: str, html_text: str) -> None:
    col.markdown(f"<div class='insight'><div class='tag'>{tag}</div>"
                 f"<div class='txt'>{html_text}</div></div>",
                 unsafe_allow_html=True)


def style_fig(fig, height: int | None = None):
    # Plotly.js renders a missing title as the literal string "undefined" once
    # title_font is set; charts labeled by an st.subheader have no plotly title,
    # so pin it to empty to suppress that.
    if fig.layout.title.text is None:
        fig.update_layout(title_text="")
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK, size=13),
        margin=dict(l=10, r=70, t=48, b=10),
        title_font=dict(family="Barlow Condensed", size=20, color="#e2e8f0"),
        hovermode="x unified", hoverlabel=dict(bgcolor="#1e293b"),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    if height:
        fig.update_layout(height=height)
    return fig


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner="Reading database...")
def load_frames(db_url: str):
    engine = db.get_engine()
    db.init_db(engine)
    # Zero-config bootstrap: auto-load the bundled demo matches only where you
    # can't scrape (a hosted deploy or a machine without the browser), so the
    # demo is never blank. On a scraping-capable machine an empty DB means
    # "start fresh" — leave it empty so the dashboard shows only what you fetch.
    if (db.summary(engine).get("matches") or 0) == 0:
        from fetch_panel import scraping_available
        if not scraping_available():
            import ingest
            ingest.ingest_raw_reports(prune=False, verbose=False)
    return (registrations_frame(engine),
            classifier_scores_frame(engine),
            db.summary(engine))


def clip_dates(df: pd.DataFrame, lo, hi) -> pd.DataFrame:
    if df.empty:
        return df
    m = (df["match_date"].dt.date >= lo) & (df["match_date"].dt.date <= hi)
    return df[m]


def field_composition(reg: pd.DataFrame, divisions: list[str],
                      freq: str) -> pd.DataFrame:
    """Period × bucket share of ALL entries (selected divisions + Other).
    Shares sum to 1 per period — feeds the 100% stacked area."""
    if reg.empty:
        return pd.DataFrame(columns=["period", "bucket", "share"])
    df = reg.assign(
        period=reg["match_date"].dt.to_period(
            {"D": "D", "W": "W", "MS": "M", "QS": "Q"}.get(freq, "M")).dt.start_time,
        bucket=reg["division"].where(reg["division"].isin(divisions), "Other"),
    )
    counts = df.groupby(["period", "bucket"]).size().rename("n").reset_index()
    counts["share"] = counts["n"] / counts.groupby("period")["n"].transform("sum")
    order = [d for d in divisions if d in counts["bucket"].unique()] + ["Other"]
    counts["bucket"] = pd.Categorical(counts["bucket"], order, ordered=True)
    return counts.sort_values(["period", "bucket"])


def growth_deltas(comp: pd.DataFrame) -> pd.DataFrame:
    """Field-share change per division: mean of last third − first third
    of the periods in range, in percentage points."""
    if comp.empty:
        return pd.DataFrame()
    periods = sorted(comp["period"].unique())
    if len(periods) < 4:
        return pd.DataFrame()
    k = max(len(periods) // 3, 1)
    first, last = set(periods[:k]), set(periods[-k:])
    rows = []
    for div, g in comp[comp["bucket"] != "Other"].groupby("bucket",
                                                          observed=True):
        a = g[g["period"].isin(first)]["share"].mean()
        b = g[g["period"].isin(last)]["share"].mean()
        if pd.notna(a) and pd.notna(b):
            rows.append({"division": str(div), "delta_pts": (b - a) * 100,
                         "now_pct": b * 100})
    return pd.DataFrame(rows).sort_values("delta_pts", ascending=False)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def main() -> None:
    reg, scores, info = load_frames(str(db.get_engine().url))

    st.title("USPSA Population Analytics")
    st.markdown(ribbon_html(), unsafe_allow_html=True)

    if reg.empty:
        st.info("The database is empty. Fetch real matches with the panel in "
                "the sidebar, or load a synthetic demo season:")
        st.code("python seed_demo.py      # synthetic demo season", language="bash")
        from datetime import date, timedelta
        with st.sidebar:
            render_fetch_panel(date.today() - timedelta(days=30), date.today())
        st.stop()

    # -- Sidebar -----------------------------------------------------------
    with st.sidebar:
        st.header("Filters")
        dmin = reg["match_date"].min().date()
        dmax = reg["match_date"].max().date()
        picked = st.date_input("Date range", (dmin, dmax),
                               min_value=dmin, max_value=dmax)
        if not (isinstance(picked, tuple) and len(picked) == 2):
            st.info("Pick both ends of the date range.")
            st.stop()
        lo, hi = picked
        gran = st.radio("Granularity", list(FREQ), horizontal=True,
                        index=list(FREQ).index(default_gran((hi - lo).days)))
        # The four mainstream handgun divisions are the analysis scope. Pills
        # (not a dropdown) so selecting all doesn't leave a "No results" menu
        # hanging open — the chips are the whole control, always visible.
        divisions = st.pills("Divisions", FOCUS_DIVISIONS,
                             selection_mode="multi", default=FOCUS_DIVISIONS)
        divisions = divisions or FOCUS_DIVISIONS  # empty selection = all four
        include_dq = st.toggle("Count DQ'd shooters in participation",
                               value=True,
                               help="A DQ'd shooter still showed up — "
                                    "participation and performance are "
                                    "different questions.")
        st.divider()
        st.subheader("Classifier thresholds")
        min_n = st.slider("Min runs per (classifier × class) cell", 3, 30, 5)
        min_classes = st.slider("Min classes per classifier", 2, 6, 3)
        present = set(scores["division"].unique()) if not scores.empty else set()
        cls_opts = [d for d in FOCUS_DIVISIONS if d in present]
        cls_divs = st.pills(
            "Divisions in classifier analysis", cls_opts,
            selection_mode="multi", default=cls_opts,
            help="Difficulty pools hit factors across the selected divisions, "
                 "so keep it to comparable ones. These four handgun divisions "
                 "shoot at similar speeds; mixing in a slower division would "
                 "distort the z-scores.")
        cls_divs = cls_divs or cls_opts  # empty selection = all four
        if st.button("Reload data"):
            load_frames.clear()
            st.rerun()
        st.divider()
        render_fetch_panel(lo, hi)

    reg_f = clip_dates(reg, lo, hi)
    scores_f = clip_dates(scores, lo, hi)
    if reg_f.empty:
        st.warning("No matches in that date range.")
        st.stop()

    trend = division_trend(reg_f, divisions, FREQ[gran], include_dq)
    comp = field_composition(reg_f if include_dq else reg_f[~reg_f["dq"].astype(bool)],
                             divisions, FREQ[gran])
    scores_c = (scores_f[scores_f["division"].isin(cls_divs)]
                if cls_divs else scores_f)
    cells = class_by_classifier(scores_c, min_n=min_n)
    diff = difficulty_scores(cells, min_classes=min_classes)

    # -- Readouts ----------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, "Matches", f"{reg_f['match_id'].nunique():,}",
        f"{lo:%b %d %Y} – {hi:%b %d %Y}")
    kpi(c2, "Entries", f"{len(reg_f):,}", "one shooter × one match")
    kpi(c3, "Unique members", f"{reg_f['member_number'].nunique():,}",
        "distinct member numbers")
    kpi(c4, "Classifier runs", f"{len(scores_f):,}",
        f"{scores_f['classifier_code'].nunique()} distinct classifiers")

    # -- Plain-language insights ------------------------------------------
    deltas = growth_deltas(comp)
    i1, i2, i3 = st.columns(3)
    if not deltas.empty:
        up, dn = deltas.iloc[0], deltas.iloc[-1]
        insight(i1, "Fastest riser",
                f"<b>{up['division']}</b> gained "
                f"<b>{up['delta_pts']:+.1f} pts</b> of field share "
                f"(now ~{up['now_pct']:.0f}% of entries).")
        insight(i2, "Steepest slide",
                f"<b>{dn['division']}</b> moved "
                f"<b>{dn['delta_pts']:+.1f} pts</b> "
                f"(now ~{dn['now_pct']:.0f}% of entries).")
    else:
        insight(i1, "Trend read", "Widen the date range for a "
                                  "first-third vs last-third comparison.")
        insight(i2, "Trend read", "—")
    if not diff.empty:
        hard = diff.iloc[0]
        insight(i3, "Hardest classifier",
                f"<b>{label_codes(pd.Series([hard['classifier_code']]))[0]}</b> — "
                f"every class averaged <b>{hard['difficulty']:.2f}σ</b> below "
                f"their own norm ({int(hard['total_runs'])} runs).")
    else:
        insight(i3, "Hardest classifier", "Not enough classifier data at "
                                          "current thresholds.")
    st.write("")

    tab_trend, tab_diff, tab_data = st.tabs(
        ["Division trends", "Classifier difficulty", "Data & methodology"])

    # ======================================================================
    with tab_trend:
        if trend.empty:
            st.warning("No registrations for the selected divisions.")
        elif trend["period"].nunique() < 2:
            st.info(
                f"Only one {gran.lower()} of data in this range — a trend line "
                "needs at least two points in time. Switch the granularity "
                "above to something finer, or select a wider date range. "
                "(The headline numbers and the classifier analysis don't need "
                "a time span — those are complete.)")
        else:
            fig = px.line(trend, x="period", y="shooters", color="division",
                          markers=True, color_discrete_map=DIVISION_COLORS,
                          labels={"period": "", "shooters": "Entries"},
                          title=f"Entries per {gran.lower()}")
            fig.update_layout(showlegend=False)
            for div, g in trend.groupby("division"):
                last = g.sort_values("period").iloc[-1]
                fig.add_annotation(x=last["period"], y=last["shooters"],
                                   text=f"<b>{DIVISION_SHORT.get(div, div)}</b>",
                                   font=dict(color=DIVISION_COLORS.get(div, INK),
                                             size=13),
                                   showarrow=False, xanchor="left", xshift=10)
            st.plotly_chart(style_fig(fig, 420), width="stretch")

            area = px.area(comp, x="period", y="share", color="bucket",
                           color_discrete_map=DIVISION_COLORS,
                           labels={"period": "", "share": "Share of field",
                                   "bucket": ""},
                           title="Composition of the whole field (100%)")
            area.update_yaxes(tickformat=".0%", range=[0, 1])
            area.update_traces(line=dict(width=0.6))
            st.plotly_chart(style_fig(area, 400), width="stretch")
            st.caption("Bands are each division's share of *all* entries "
                       "that period; gray is every other division combined. "
                       "The top chart shows raw turnout; this one shows who "
                       "is taking share from whom.")

            mp = matches_per_period(reg_f, FREQ[gran])
            bars = px.bar(mp, x="period", y="matches",
                          labels={"period": "", "matches": "Matches"},
                          title="Sample size: matches ingested per period")
            bars.update_traces(marker_color="#334155")
            st.plotly_chart(style_fig(bars, 260), width="stretch")

    # ======================================================================
    with tab_diff:
        if diff.empty:
            st.warning("Not enough classifier data at these thresholds. "
                       "Lower the sliders or ingest more matches.")
        else:
            st.subheader("Stage difficulty, skill-adjusted")
            st.caption("Each class's mean hit factors are z-scored across "
                       "classifiers — removing that class's own pace — then "
                       "averaged per stage. Higher = everyone from GM to D "
                       "shot it below their norm.")
            d = diff.copy()
            d["label"] = label_codes(d["classifier_code"])
            d = d.sort_values("difficulty")
            bar = px.bar(d, x="difficulty", y="label", orientation="h",
                         color="difficulty",
                         color_continuous_scale=["#facc15", "#f97316", "#ef4444"],
                         hover_data={"total_runs": True, "classes_used": True,
                                     "overall_mean_hf": ":.2f",
                                     "label": False, "difficulty": ":.2f"},
                         labels={"difficulty": "Difficulty (−mean z)",
                                 "label": ""})
            bar.update_layout(coloraxis_showscale=False)
            # Classifier codes like "25-08" look like dates to Plotly's axis
            # auto-detection; pin the axis to categorical so they render as
            # labels, not a time axis.
            bar.update_yaxes(type="category")
            st.plotly_chart(style_fig(bar, max(380, 30 * len(d) + 120)),
                            width="stretch")

            st.subheader("Mean hit factor · classification × classifier")
            wide = hf_heatmap_table(cells, order_by=diff)
            wide.index = label_codes(pd.Series(wide.index))
            hm = px.imshow(wide, text_auto=".2f", aspect="auto",
                           color_continuous_scale="Viridis",
                           labels=dict(x="", y="", color="Mean HF"))
            hm.update_yaxes(type="category")  # codes aren't dates (see above)
            hm.update_xaxes(type="category")
            st.plotly_chart(style_fig(hm, max(380, 30 * len(wide) + 140)),
                            width="stretch")
            st.caption("Read a row left→right for the skill gradient on one "
                       "stage; compare within a column for stage difficulty "
                       "at fixed skill. Hardest stages on top.")

            st.subheader("Distribution on a single classifier")
            pick = st.selectbox(
                "Classifier", diff["classifier_code"].tolist(),
                format_func=lambda c: label_codes(pd.Series([c]))[0])
            sel = scores_c[scores_c["classifier_code"] == pick]
            box = px.box(sel, x="classification", y="hit_factor",
                         color="classification", points="outliers",
                         category_orders={"classification": CLASS_ORDER},
                         color_discrete_map=CLASS_COLORS,
                         labels={"classification": "", "hit_factor": "Hit factor"})
            box.update_layout(showlegend=False)
            st.plotly_chart(style_fig(box, 420), width="stretch")
            st.caption(f"{len(sel):,} valid runs on this classifier in range. "
                       "DQ, DNF, and zero-HF runs are excluded.")

    # ======================================================================
    with tab_data:
        st.subheader("Difficulty methodology")
        st.markdown(
            "Raw mean hit factor confounds *shooter skill* with *stage "
            "difficulty*. For each classification $k$ with cell means "
            "$\\overline{HF}_{c,k}$ across classifiers $c$,\n\n"
            "$$z_{c,k} = \\frac{\\overline{HF}_{c,k} - \\mu_k}{\\sigma_k}"
            "\\qquad D_c = -\\tfrac{1}{K}\\sum_k z_{c,k}$$\n\n"
            "Z-scoring **within a class, across classifiers** removes each "
            "class's overall pace, so what remains is how the *stage* moved "
            "everyone relative to their own norm. Cells need the sidebar "
            "minimum runs; classifiers need the sidebar minimum classes; a "
            "class column must span ≥ 2 classifiers or σ is undefined.")

        st.subheader("Tables")
        with st.expander("Per-cell classifier table (n / mean / median HF)"):
            st.dataframe(cells, width="stretch", hide_index=True)
            st.download_button("Download CSV",
                               cells.to_csv(index=False).encode(),
                               "classifier_cells.csv", "text/csv")
        with st.expander("Registrations (participation fact table)"):
            st.dataframe(reg_f.head(1000), width="stretch", hide_index=True)
            st.download_button("Download CSV",
                               reg_f.to_csv(index=False).encode(),
                               "registrations.csv", "text/csv")

        st.subheader("Provenance")
        st.markdown(
            "- Source: PractiScore **Web Report** text files linked from "
            "each match's results page, harvested during a browser session "
            "you drive yourself (`scrape.py`). Hit factors arrive "
            "precomputed in that report.\n"
            "- Classifier titles: bundled reference list "
            "(`data/reference/classifier_titles.csv`, Apache-2.0, from "
            "kmcken/CompetitionShootingAnalytics).\n"
            "- Demo data from `seed_demo.py` is synthetic; its trends are "
            "invented and must not be presented as real.")


main()
