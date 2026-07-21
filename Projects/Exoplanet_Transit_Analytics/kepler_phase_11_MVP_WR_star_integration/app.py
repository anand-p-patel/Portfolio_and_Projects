"""
Kepler PINN — public dashboard (Phase 9).

Run with:  streamlit run app.py

Two view modes:
  - Single target: full diagnostics for one star — transit targets get
    BLS metrics, the folded transit with the PINN model overlaid, and
    the transit scene; variability targets get period/amplitude/RMS.
    Every target gets its simulated host-star portrait.
  - Compare targets: any user-selected set of processed stars side by
    side — parameter table, star gallery at relative physical scale,
    overlaid folded transits.

Reads processed results from SQLite; never re-runs the heavy pipeline
on page load, and never imports torch — PINN curves are served as
plain arrays written at training time.
"""

import random

import numpy as np
import pandas as pd
import streamlit as st

from db import storage, catalog
from viz import plots
from pipeline import vetting as vet_mod

st.set_page_config(page_title="MAST Data Analytics",
                   page_icon="\U0001FA90", layout="wide")

storage.init_db()


@st.cache_data(ttl=24 * 3600, show_spinner="Loading mission catalogue…")
def load_catalog(mission):
    """
    Cached full catalogue for a mission; returns (entries, error_message).
    entries: list of {name, status, period_days, prad_earth}.
    """
    try:
        return catalog.fetch_catalog(mission), None
    except Exception as exc:  # network/offline — degrade gracefully
        return [], str(exc)


def _pick_random(options):
    """Random-button callback. Setting the widget value in a callback
    (before the widget re-instantiates) is the supported pattern —
    assigning it in the script body after the selectbox raises."""
    if options:
        st.session_state.target_id = random.choice(options)


def _have(module):
    """True if an importable module is present (without importing it)."""
    from importlib.util import find_spec
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def run_analysis(name, mission, train_pinn, quick, wr_star=None):
    """
    Run the full pipeline for one object, inline, with live status.
    Heavy deps (lightkurve, torch) are imported lazily here so the base
    dashboard never pulls them in. For a Wolf-Rayet star (wr_star dict)
    it runs the variability path with literature Teff/radius/period;
    otherwise the transit path. Returns (ok, error_message).
    """
    try:
        from pipeline.ingest import fetch_light_curve, get_stellar_params
        from run_pipeline import process_transit, process_variability
    except Exception as exc:
        return False, f"pipeline unavailable: {exc}"

    try:
        with st.status(f"Analyzing {name}…", expanded=True) as status:
            st.write("Searching MAST and downloading the light curve…")
            if wr_star:
                lc = fetch_light_curve(wr_star["ident"], mission="TESS",
                                       quarters=2 if quick else None)
            else:
                lc = fetch_light_curve(name, mission=mission,
                                       quarters=1 if quick else None)
            if lc is None:
                status.update(label="No light curve found", state="error")
                return False, f"No light curve found for {name}."

            if wr_star:
                st.write("Lomb-Scargle + SHO-PINN (coherence)…")
                process_variability(
                    name, "Wolf-Rayet", lc, teff=wr_star["teff"],
                    stellar_radius=wr_star["radius"], use_pinn=train_pinn,
                    period_hint=wr_star["period_days"])
            else:
                teff, radius = get_stellar_params(lc)
                st.write("Detrending, running BLS"
                         + (", training the PINN" if train_pinn else "") + "…")
                process_transit(name, mission, lc, window=None,
                                teff=teff, stellar_radius=radius,
                                use_pinn=train_pinn, mask_transits=True,
                                vet=True)
            status.update(label=f"{name} analyzed", state="complete")
        return True, None
    except Exception as exc:
        return False, str(exc)


def show_unanalyzed(name, entry, mission):
    """Main-area panel for a catalogue object with no local pipeline run."""
    status = entry.get("status") if entry else None
    kind = {"confirmed": "Confirmed transiting planet host",
            "candidate": "Candidate — still being vetted"}.get(
                status, "Catalogue object")
    st.title(name)
    st.caption(f"{mission} · {kind} · not yet analyzed locally")

    c1, c2 = st.columns(2)
    period = entry.get("period_days") if entry else None
    prad = entry.get("prad_earth") if entry else None
    c1.metric("Archive period",
              f"{period:.4f} d" if period is not None else "—")
    c2.metric("Archive radius",
              f"{prad:.2f} R⊕" if prad is not None else "—")

    cmd = f'python run_pipeline.py --targets "{name}" --mission {mission} --pinn'

    if not _have("lightkurve"):
        # Hosted deploy without the ingestion stack — offer the command.
        st.info("This dashboard instance can't run the pipeline "
                "(ingestion dependencies aren't installed here). Run it "
                "locally:")
        st.code(cmd)
    else:
        st.info("Not analyzed yet — run the pipeline right here:")
        torch_ok = _have("torch")
        c1, c2 = st.columns(2)
        train = c1.checkbox(
            "Train PINN", value=torch_ok, disabled=not torch_ok,
            help=None if torch_ok else "torch isn't installed here")
        quick = c2.checkbox(
            "Quick (1 quarter)", value=False,
            help="One quarter/sector — faster, fewer transits, less "
                 "accurate depth")
        if st.button(f"▶ Analyze {name} now", type="primary",
                     width="stretch"):
            ok, err = run_analysis(name, mission, train, quick)
            if ok:
                st.rerun()
            else:
                st.error(f"Analysis failed: {err}")
        with st.expander("…or run it from the command line"):
            st.code(cmd)

    st.caption(
        "Archive period and radius are the catalogue's vetting values, not "
        "a measurement from this pipeline."
    )


def render_vetting(data, bls):
    """Phase 10 vetting report — disposition + per-test breakdown, computed
    live from the stored light curve (centroid, if any, comes from the DB)."""
    v = vet_mod.vet_lightcurve(data["time"], data["flux"],
                               bls["period_days"], bls["t0"],
                               bls["duration_days"])
    disp = v["disposition"]
    st.subheader("Vetting report")
    banner = {"candidate": st.success, "review": st.warning,
              "false_positive": st.error, "low_snr": st.warning}[disp]
    icon = {"candidate": "✅", "review": "⚠️",
            "false_positive": "\U0001F6A9", "low_snr": "•"}[disp]
    head = f"{icon} **{vet_mod.DISPOSITION_LABEL[disp]}**"
    if v["flags"]:
        head += f" — {v['flags'][0]}"
    banner(head)

    def fmt(x, spec="{:.1f}"):
        return spec.format(x) if x is not None and np.isfinite(x) else "—"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transit SNR", fmt(v["snr"], "{:.0f}"),
              help="depth·√N / out-of-transit noise; detection floor ≈ 7")
    c2.metric("Odd/even", fmt(v["oddeven_sigma"]) + " σ",
              help="Odd- vs even-numbered transit depth agreement. A big "
                   "difference means an eclipsing binary at 2× the period.")
    c3.metric("Secondary", fmt(v["secondary_snr"], "{:.0f}") + " σ",
              help="Eclipse at phase 0.5. Deep = stellar companion, or a "
                   "period alias if it equals the primary.")
    c4.metric("Rp / R★", fmt(v["rp_over_rstar"], "{:.3f}"),
              help="Above 0.18 is a stellar radius ratio, not a planet.")

    for extra in v["flags"][1:]:
        st.caption("\U0001F6A9 " + extra)

    stored = data.get("vetting") or {}
    if stored.get("centroid_note"):
        st.caption("Centroid test: " + stored["centroid_note"])
    else:
        st.caption("Odd/even and secondary-eclipse tests catch eclipsing "
                   "binaries; SNR gates significance. Run the pipeline with "
                   "`--centroid` to add the background-blend test.")


def show_wr_unanalyzed(name, star):
    """Pending-analysis panel for a curated Wolf-Rayet star, with a
    physics-simulated portrait from its literature Teff."""
    if star is None:
        st.title(name)
        st.info("Unknown Wolf-Rayet star.")
        return
    st.title(name)
    st.caption(f"Wolf-Rayet star · {star['note']} · photometry from TESS")
    left, right = st.columns([3, 2])
    with right:
        st.pyplot(plots.render_star(star["teff"], star["radius"], name=name))
        st.caption("Simulated from literature Teff (Planck's law) — a hot, "
                   "blue Wolf-Rayet star, not a stock image.")
    with left:
        m1, m2, m3 = st.columns(3)
        m1.metric("Teff", f"{star['teff']:,} K")
        m2.metric("Radius", f"{star['radius']:.1f} R☉")
        m3.metric("Period",
                  f"{star['period_days']:.2f} d" if star["period_days"] else "—")
        if not _have("lightkurve"):
            st.info("Run locally to fit its variability:")
            st.code(f'python run_pipeline.py --targets "{star["ident"]}" '
                    "--mission TESS --mode variability --pinn")
        else:
            st.info("Not analyzed yet — fit its wind variability and "
                    "coherence right here:")
            torch_ok = _have("torch")
            c1, c2 = st.columns(2)
            train = c1.checkbox("Train SHO-PINN (Q)", value=torch_ok,
                                disabled=not torch_ok,
                                help=None if torch_ok else "torch not installed")
            quick = c2.checkbox("Quick (2 sectors)", value=True)
            if st.button(f"▶ Analyze {name} now", type="primary",
                         width="stretch"):
                ok, err = run_analysis(name, "Wolf-Rayet", train, quick,
                                       wr_star=star)
                if ok:
                    st.rerun()
                else:
                    st.error(f"Analysis failed: {err}")
    st.caption("Wolf-Rayet winds are largely stochastic — expect a low "
               "quality factor Q. Compare with the coherent synthetic "
               "pulsator SYNTH-VAR (Q ≈ 88).")


def wr_sidebar_and_load(analyzed):
    """Sidebar picker for the Wolf-Rayet mission; returns the loaded target
    (or renders the pending panel and stops)."""
    wr_names = sorted(set(catalog.WR_BY_NAME) | analyzed)
    if st.session_state.get("target_id") not in wr_names:
        prefer = sorted(analyzed & set(wr_names))
        st.session_state.target_id = prefer[0] if prefer else wr_names[0]
    st.sidebar.selectbox(
        f"Wolf-Rayet star ({len(wr_names)})", wr_names, key="target_id",
        format_func=lambda n: ("\U0001F4CA " if n in analyzed
                               else "⭐ ") + n)
    st.sidebar.button("\U0001F3B2 Random", on_click=_pick_random,
                      args=(wr_names,), width="stretch")
    st.sidebar.caption("📊 analyzed here · ⭐ catalogue (click to analyze)")
    st.sidebar.divider()
    st.sidebar.caption('Analyze from the command line:\n\n'
                       '`python run_pipeline.py --targets "HD 50896" '
                       '--mission TESS --mode variability --pinn`')
    data = storage.load_target(st.session_state.target_id)
    if data is None:
        show_wr_unanalyzed(st.session_state.target_id,
                           catalog.WR_BY_NAME.get(st.session_state.target_id))
        st.stop()
    return data


def archive_sidebar_and_load(analyzed):
    """Sidebar pickers for a survey mission (analyzed / confirmed /
    candidates over the archive catalogue); returns the loaded target (or
    renders the pending panel and stops)."""
    entries, cat_err = load_catalog(st.session_state.mission)
    entry_by_name = {e["name"]: e for e in entries}
    analyzed_opts = sorted(analyzed)
    confirmed = sorted({e["name"] for e in entries
                        if e["status"] == "confirmed"} - analyzed)
    candidates = sorted({e["name"] for e in entries
                         if e["status"] == "candidate"} - analyzed)
    universe = set(analyzed_opts) | set(confirmed) | set(candidates)

    if cat_err:
        st.sidebar.caption("Catalogue offline — analyzed targets only.")
    if st.session_state.get("target_id") not in universe:
        st.session_state.target_id = (analyzed_opts or confirmed
                                      or candidates)[0]
    tid = st.session_state.target_id
    for key, opts in (("sel_analyzed", analyzed_opts),
                      ("sel_confirmed", confirmed),
                      ("sel_candidate", candidates)):
        if not opts:
            st.session_state.pop(key, None)
        elif tid in opts:
            st.session_state[key] = tid
        elif st.session_state.get(key) not in opts:
            st.session_state[key] = opts[0]

    def _use(key):
        st.session_state.target_id = st.session_state[key]

    st.sidebar.selectbox(
        f"\U0001F4CA Analyzed by local PINN ({len(analyzed_opts)})",
        analyzed_opts, key="sel_analyzed",
        on_change=_use, args=("sel_analyzed",))
    if confirmed:
        st.sidebar.selectbox(
            f"✅ Confirmed planets ({len(confirmed):,})",
            confirmed, key="sel_confirmed",
            on_change=_use, args=("sel_confirmed",))
    if candidates:
        st.sidebar.selectbox(
            f"\U0001F7E1 Candidates — being vetted ({len(candidates):,})",
            candidates, key="sel_candidate",
            on_change=_use, args=("sel_candidate",))

    st.sidebar.button("\U0001F3B2 Random", on_click=_pick_random,
                      args=(sorted(universe),), width="stretch")
    st.sidebar.caption(f"Viewing **{tid}**")
    st.sidebar.divider()
    st.sidebar.caption(
        "Process new targets from the command line:\n\n"
        "`python run_pipeline.py --targets Kepler-17 --pinn`\n\n"
        "`python run_pipeline.py --range Kepler 8 12`"
    )
    data = storage.load_target(st.session_state.target_id)
    if data is None:
        show_unanalyzed(st.session_state.target_id,
                        entry_by_name.get(st.session_state.target_id),
                        st.session_state.mission)
        st.stop()
    return data


st.sidebar.title("MAST Data Analytics")
st.sidebar.caption("Kepler · K2 · TESS · Wolf-Rayet — transits, vetting "
                   "& variability")

if not storage.list_targets():
    st.title("No targets processed yet")
    st.markdown(
        "Populate the database first:\n\n"
        "```bash\n"
        "python run_pipeline.py --synthetic --pinn\n"
        "python run_pipeline.py --targets Kepler-8 Kepler-10 --pinn\n"
        "python run_pipeline.py --range Kepler 8 12\n"
        "```"
    )
    st.stop()

# Mission -> object selection (Phase 6 / task 7). The mission scopes the
# object list below to one telescope.
missions = storage.list_missions()
if ("mission" not in st.session_state
        or st.session_state.mission not in missions):
    st.session_state.mission = missions[0]
st.sidebar.selectbox("Mission", missions, key="mission",
                     help="Kepler / K2 / TESS transit surveys, or the "
                          "Wolf-Rayet variable-star set (Phase 7).")
targets = storage.list_targets_for_mission(st.session_state.mission)

mode = st.sidebar.radio("View mode", ["Single target", "Compare targets"])

# ======================================================================
# Single-target view
# ======================================================================
if mode == "Single target":
    analyzed = set(targets)
    # Wolf-Rayet is its own mission (curated catalogue, variability mode);
    # everything else uses the archive catalogue with confirmed/candidate
    # pickers.
    if st.session_state.mission == "Wolf-Rayet":
        data = wr_sidebar_and_load(analyzed)
    else:
        data = archive_sidebar_and_load(analyzed)

    bls = data["results"].get("bls")
    pinn = data["results"].get("pinn")
    var = data["results"].get("variability")

    st.title(data["target_id"])
    star_bits = []
    if data["teff"] is not None:
        star_bits.append(f"{plots.spectral_class(data['teff'])}-type")
        star_bits.append(f"{data['teff']:.0f} K")
    if data["stellar_radius"] is not None:
        star_bits.append(f"{data['stellar_radius']:.2f} R\u2609")
    star_txt = " \u00b7 ".join(star_bits) if star_bits \
        else "stellar parameters unavailable"
    mission_label = (f"{data['mission']} \u00b7 TESS photometry"
                     if data["mission"] == "Wolf-Rayet"
                     else f"Mission: {data['mission']}")
    st.caption(
        f"{mission_label} \u00b7 {star_txt} "
        f"\u00b7 {data['n_points']:,} data points "
        f"\u00b7 processed {data['processed_at']}"
    )

    if bls:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Period", f"{bls['period_days']:.4f} d")
        c2.metric("Transit depth", f"{bls['depth'] * 100:.3f} %")
        c3.metric("Rp / R\u2605", f"{bls['rp_over_rstar']:.4f}")
        c4.metric("Duration", f"{bls['duration_days'] * 24:.2f} h")
    elif var:
        pvar = data["results"].get("pinn_var")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Period", f"{var['period_days']:.4f} d")
        c2.metric("Amplitude", f"{var['amplitude'] * 100:.2f} %")
        c3.metric("RMS", f"{var['rms'] * 100:.2f} %")
        if pvar and pvar.get("quality_factor") is not None:
            q = pvar["quality_factor"]
            c4.metric("Quality factor Q", f"{q:.1f}",
                      help="SHO coherence from the autocorrelation. High = "
                           "coherent pulsation; low = stochastic wind.")

    if bls:
        render_vetting(data, bls)

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Light curve")
        title = ("Flattened light curve" if bls
                 else "Normalized light curve (not detrended)")
        st.pyplot(plots.plot_light_curve(data["time"], data["flux"],
                                         title=title))

        if bls:
            st.subheader("Phase-folded transit")
            st.pyplot(plots.plot_folded(
                data["time"], data["flux"],
                period=bls["period_days"], t0=bls["t0"],
                duration=bls["duration_days"],
                model_phase=data.get("pinn_phase"),
                model_flux=data.get("pinn_flux"),
            ))
            if data.get("pinn_phase") is not None:
                st.caption(
                    "Green curve: the Phase 4 PINN's fitted profile — "
                    "transit geometry and flux conservation enforced in "
                    "the loss. Served from stored arrays; the dashboard "
                    "never loads torch."
                )
        elif var:
            st.subheader("Phase-folded variability")
            pvar = data["results"].get("pinn_var")
            model_period = (pvar["period_days"] if pvar
                            else var["period_days"])
            st.pyplot(plots.plot_folded_variability(
                data["time"], data["flux"], period=model_period,
                model_phase=data.get("pinn_var_phase"),
                model_flux=data.get("pinn_var_flux"),
            ))
            if pvar and data.get("pinn_var_flux") is not None:
                q = pvar["quality_factor"]
                verdict = ("coherent pulsation / rotation"
                           if q > 30 else "stochastic wind (low coherence)")
                st.caption(
                    f"Green curve: the Phase 7 SHO-PINN model. Quality "
                    f"factor **Q = {q:.1f}** → {verdict}. Q is the damped-"
                    "oscillator coherence read from the light curve's "
                    "autocorrelation; the fold is clean when Q is high and "
                    "washes out when it is low."
                )

    with right:
        st.subheader("Host star (simulated)")
        st.pyplot(plots.render_star(
            data["teff"], data["stellar_radius"], name=data["target_id"],
        ))
        st.caption(
            "Simulated from catalogue physics: colour from Planck's law "
            "at the star's measured Teff, limb darkening varying with "
            "temperature. Not a stock image."
        )

        if bls:
            st.subheader("Transit scene (to scale)")
            st.pyplot(plots.render_transit_scene(
                bls["rp_over_rstar"], teff=data["teff"],
            ))
            st.caption(
                "Planet silhouette at the pipeline's own measured "
                "Rp/R\u2605 \u2014 the image is the measurement."
            )

            st.subheader("Model comparison")
            if pinn:
                st.metric(
                    "PINN Rp / R\u2605", f"{pinn['rp_over_rstar']:.4f}",
                    delta=f"{pinn['rp_over_rstar'] - bls['rp_over_rstar']:+.4f}",
                )
                st.caption(
                    "Delta vs the classical BLS baseline. The PINN fits a "
                    "smooth, physics-constrained transit profile; on clean "
                    "single-transit targets the two agree to a few percent."
                )
            else:
                st.info(
                    "No PINN result stored for this target yet. Re-run "
                    "the pipeline with `--pinn` to train Phase 4 here."
                )
        elif var:
            st.subheader("Analysis mode")
            st.info(
                "Variability target (Phase 7 baseline): Lomb-Scargle "
                "period search on the un-flattened light curve. "
                "Transit metrics do not apply."
            )

    if bls:
        with st.expander("ETL before / after (Phase 2 detrending)"):
            st.pyplot(plots.plot_raw_vs_flat(
                data["raw_time"], data["raw_flux"],
                data["time"], data["flux"],
            ))

# ======================================================================
# Compare view
# ======================================================================
else:
    default_sel = targets[: min(3, len(targets))]
    sel = st.sidebar.multiselect(
        f"Compare {st.session_state.mission} targets", targets,
        default=default_sel)

    st.title("Target comparison")
    if not sel:
        st.info("Pick one or more targets in the sidebar.")
        st.stop()

    loaded = [d for d in (storage.load_target(t) for t in sel)
              if d is not None]

    rows = []
    for d in loaded:
        b = d["results"].get("bls") or {}
        p = d["results"].get("pinn") or {}
        v = d["results"].get("variability") or {}
        rows.append({
            "Target": d["target_id"],
            "Class": plots.spectral_class(d["teff"]),
            "Teff (K)": (None if d["teff"] is None
                         else int(round(d["teff"]))),
            "R\u2605 (R\u2609)": (None if d["stellar_radius"] is None
                                  else round(d["stellar_radius"], 2)),
            "Period (d)": (round(b["period_days"], 4) if b.get("period_days")
                           else (round(v["period_days"], 4)
                                 if v.get("period_days") else None)),
            "Depth (%)": (None if b.get("depth") is None
                          else round(100 * b["depth"], 3)),
            "Rp/R\u2605 (BLS)": (None if b.get("rp_over_rstar") is None
                                 else round(b["rp_over_rstar"], 4)),
            "Rp/R\u2605 (PINN)": (None if p.get("rp_over_rstar") is None
                                  else round(p["rp_over_rstar"], 4)),
            "Amp (%)": (None if v.get("amplitude") is None
                        else round(100 * v["amplitude"], 2)),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.subheader("Host stars (simulated, sizes to relative scale)")
    radii = [d["stellar_radius"] if d["stellar_radius"] else 1.0
             for d in loaded]
    rmax = max(radii)
    cols = st.columns(len(loaded))
    for col, d, r in zip(cols, loaded, radii):
        scale = max(0.25, r / rmax)
        col.pyplot(plots.render_star(
            d["teff"], d["stellar_radius"],
            name=d["target_id"], scale=scale,
        ))

    entries = [
        {
            "label": d["target_id"],
            "time": d["time"], "flux": d["flux"],
            "period": b["period_days"], "t0": b["t0"],
            "duration": b["duration_days"],
        }
        for d in loaded
        if (b := d["results"].get("bls"))
    ]
    if len(entries) >= 2:
        st.subheader("Folded transit comparison")
        st.pyplot(plots.plot_folded_comparison(entries))
        st.caption(
            "Binned median transit profile for each star, folded at its "
            "own detected period. Depth differences are direct Rp/R\u2605 "
            "differences."
        )
