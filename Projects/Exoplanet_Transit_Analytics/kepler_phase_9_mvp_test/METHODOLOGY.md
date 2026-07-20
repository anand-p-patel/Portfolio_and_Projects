# Methodology — Kepler Transit Analytics Engine

> Full technical write-up: physics, validation, architecture, and roadmap.
> For a 30-second setup, see [README.md](README.md).

An end-to-end pipeline that ingests Kepler space telescope photometry,
isolates exoplanet transit signals from instrument drift, measures the
planet-to-star radius ratio with both a classical baseline and a
Physics-Informed Neural Network, and serves everything through an
interactive dashboard.

The physics: when a planet crosses its star, the fractional drop in
light obeys the geometry of two intersecting discs,

    Delta F = (Rp / R*)^2

so a careful measurement of transit depth is a direct measurement of
planetary size. Every number and image in the dashboard derives from
that relation applied to real (or synthetic ground-truth) photometry.

## Validation (synthetic ground truth, fully offline)

| Target       | Truth Rp/R* | BLS baseline | PINN   |
|--------------|-------------|--------------|--------|
| SYNTH-DEMO   | 0.0949      | 0.0938       | 0.0948 |
| SYNTH-DEMO-B | 0.1265      | 0.1251       | 0.1246 |

| Target    | Truth P (d) | Truth amp | Recovered P | Recovered amp |
|-----------|-------------|-----------|-------------|----------------|
| SYNTH-VAR | 0.8500      | 0.0200    | 0.8519      | 0.0197         |

Both transit methods run on data carrying a known ~2% systematic depth
bias from Savitzky-Golay detrending. On SYNTH-DEMO the PINN's
physics-constrained smooth profile recovers the true depth to 0.1% —
through the bias the BLS box fit cannot escape (a box average over
ingress/egress underestimates the floor of the U). On the wider
transit of SYNTH-DEMO-B the two methods are comparable: detrending
erosion grows with the duration-to-window ratio, which is exactly the
motivation for transit-masked flattening (Phase 5b).

## Architecture

    [ Phase 1: Ingestion ] -> [ Phase 2: ETL ] -> [ Phase 3: BLS baseline ]
                                                       |
                              [ SQLite results ] <-----+----> [ Phase 4: PINN ]
                                      |
                              [ Streamlit dashboard ]

- `pipeline/ingest.py` — downloads light curves from the MAST archive
  (lightkurve), mission-parameterised (`--mission Kepler|K2|TESS`),
  and extracts the host star's Teff and radius from the FITS header.
- `pipeline/transform.py` — Savitzky-Golay detrending, with a
  documented guard against the filter biasing transit depth.
- `pipeline/analyze.py` — the classical baselines: Box Least Squares
  transit search (transit mode) and Lomb-Scargle period search with
  amplitude/RMS (variability mode; light curves are NOT flattened in
  this mode — the detrender would erase the signal).
- `pipeline/pinn.py` — the Physics-Informed Neural Network,
  implemented and annotated as a study document. Fourier-feature
  input encoding (Tancik et al. 2020) defeats spectral bias — the
  file documents the v1 failure that motivated it. A learnable depth
  parameter is tied to the fitted curve through a transit-geometry
  loss term, with a flux-conservation term and a lambda warmup
  schedule. BLS seeds the ephemeris; the PINN refines profile and
  depth.
- `pipeline/synthetic.py` — three ground-truth demo targets (Sun-like
  G, K dwarf, hot variable) so every mode of the pipeline, the star
  rendering, and the dashboard demo offline.
- `db/storage.py` — SQLite metadata + results; bulk arrays as
  compressed .npz. One `method` column holds bls, pinn, and
  variability rows side by side; columns arrive via lightweight
  in-place migrations. PINN model curves are stored as plain arrays
  at training time, so the dashboard serves them without importing
  torch (train offline, serve artifacts).
- `viz/plots.py` — light curves, folded transits with PINN overlay,
  folded comparisons, and simulated star imagery: colour from
  Planck's law at the catalogued Teff (CIE colour-matching fits of
  Wyman, Sloan & Shirley 2013), temperature-dependent limb darkening,
  planet silhouettes to scale from the measured Rp/R*.
- `app.py` — Streamlit dashboard: single-target diagnostics (transit
  or variability), BLS-vs-PINN model comparison, simulated host-star
  portraits, multi-target comparison with a star gallery at relative
  physical scale, and random-target exploration.

## Quick start

    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

    # Offline demo — three ground-truth stars, PINN included:
    python run_pipeline.py --synthetic --pinn

    # Real targets (downloads from MAST):
    python run_pipeline.py --targets Kepler-8 Kepler-10 --pinn
    python run_pipeline.py --range Kepler 8 12
    python run_pipeline.py --targets "TIC 470710327" --mission TESS --mode variability

    streamlit run app.py

Note: PyTorch currently requires Python <= 3.13; create the venv with
`py -3.12 -m venv .venv` on Windows if your default Python is newer.

## Roadmap

- [x] Phase 1–2: ingestion + ETL (validated against synthetic ground truth)
- [x] Phase 3: BLS baseline analysis
- [x] Phase 4: PINN — transit geometry + flux conservation in the
      loss; validated against ground truth and the BLS baseline
- [x] Phase 5: batch CLI over user-supplied targets and ranges
- [x] Phase 7 (baseline): variability mode — Lomb-Scargle period,
      amplitude, RMS on un-flattened light curves
- [x] Phase 8: SQLite persistence with stellar characterisation
- [x] Phase 9: Streamlit dashboard — single/compare modes, PINN
      overlay, physics-simulated star imagery
- [ ] Phase 4b/5b: transit-masked detrending to remove the measured
      ~2% systematic depth bias
- [ ] Phase 5c: multi-quarter stitching for more transits per target
- [ ] Phase 6: TESS validation — the mission parameter is threaded
      end-to-end; real-archive testing pending
- [ ] Phase 7 (full): Wolf-Rayet-specific physics loss on the
      variability branch
- [ ] Validate real-target Rp/R* against the NASA Exoplanet Archive
- [ ] Deployment: Streamlit Community Cloud

Built with [lightkurve](https://lightkurve.github.io/lightkurve/),
NumPy, PyTorch, Matplotlib, SQLite, and Streamlit.
