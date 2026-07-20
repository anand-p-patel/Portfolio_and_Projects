# Kepler Transit Analytics — Claude Code Handoff Brief

## What this project is

An end-to-end exoplanet transit detection pipeline. It downloads
Kepler photometry from the MAST archive, removes instrument drift,
finds periodic transit signals with Box Least Squares (BLS), then
refines the planet-to-star radius ratio (Rp/R★) with a
Physics-Informed Neural Network (PINN) whose loss function encodes
the transit geometry law:

    Delta F = (Rp / R*)^2

The Streamlit dashboard serves results, simulated star portraits
(colour computed from Planck's law at the catalogued Teff), and
transit scenes with the planet drawn to scale.

## Current state

**Phases complete and validated:** 1 (ingestion), 2 (ETL/flatten),
3 (BLS baseline), 4 (PINN), 5 (batch CLI + range expansion),
7-baseline (Lomb-Scargle variability mode), 8 (SQLite), 9 (Streamlit
dashboard).

**Validation numbers (synthetic ground truth, fully reproducible):**

| Target       | Truth Rp/R★ | BLS    | PINN   |
|--------------|-------------|--------|--------|
| SYNTH-DEMO   | 0.0949      | 0.0938 | 0.0941 |
| SYNTH-DEMO-B | 0.1265      | 0.1251 | 0.1245 |

Variability mode: SYNTH-VAR period 0.8519 d (truth 0.85), amp 0.0197
(truth 0.02).

**Known systematic:** Single-quarter Savitzky-Golay flattening biases
transit depth ~2% low. Kepler-8 real-data result: PINN Rp/R★ ≈ 0.0719
vs published ≈ 0.096. Cause is understood (flatten erodes transit floor
+ single quarter). Fix is Phase 5b + 4b (see roadmap below).

## Project structure

```
kepler_test/
├── app.py                   # Streamlit dashboard (Phase 9)
├── run_pipeline.py          # Batch CLI runner (Phase 5)
├── requirements.txt
├── kepler.db                # SQLite results database
├── pipeline/
│   ├── ingest.py            # Phase 1: MAST download via lightkurve
│   ├── transform.py         # Phase 2: Savitzky-Golay detrend
│   ├── analyze.py           # Phase 3: BLS + Phase 7: Lomb-Scargle
│   ├── pinn.py              # Phase 4: PINN (implemented + annotated)
│   └── synthetic.py         # 3 ground-truth demo targets
├── db/
│   └── storage.py           # SQLite CRUD layer
├── viz/
│   └── plots.py             # Light curves, folded transits, star imagery
└── data/processed/          # Compressed .npz arrays per target
```

## Environment

- Python 3.13 venv (torch requires Python <= 3.13)
- Activate: `.venv\Scripts\activate.bat` (cmd) or set execution policy
  for PowerShell
- Install: `python -m pip install -r requirements.txt`
- Run synthetic validation: `python run_pipeline.py --synthetic --pinn`
- Run dashboard: `python -m streamlit run app.py`

## Stack

`lightkurve`, `numpy`, `pandas`, `matplotlib`, `torch`, `streamlit`,
`sqlite3` (stdlib)

## CLI usage

```bash
# Offline demo (no internet, known ground truth):
python run_pipeline.py --synthetic --pinn

# Real targets:
python run_pipeline.py --targets Kepler-8 Kepler-10 --pinn
python run_pipeline.py --range Kepler 8 17 --pinn

# Variability mode (e.g. TESS variable stars):
python run_pipeline.py --targets "TIC 470710327" --mission TESS --mode variability
```

## Immediate next tasks (in priority order)

### 1. NASA Exoplanet Archive validation table

Run `--range Kepler 8 17 --pinn`, then fetch published Rp/R★ from the
NASA Exoplanet Archive API for each target and build a comparison table.
The API endpoint is:

```
https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+pl_name,pl_rade,pl_radj,st_rad+from+pscomppars+where+hostname+like+%27Kepler-8%27&format=json
```

Add a `validate.py` script that queries the archive for a list of
target names and prints the comparison table (published vs BLS vs PINN).
This table goes in README.md and is the centrepiece of the portfolio.

### 2. Phase 5b — multi-quarter stitching

In `pipeline/ingest.py`, `fetch_light_curve()` currently downloads only
`search_result[0]` (one quarter, ~90 days, ~8 transits for a 3.5 d
period). Replace with:

```python
collection = search_result.download_all()
lc = collection.stitch()
```

More quarters = more transits stacked = deeper SNR in the fold =
more accurate depth. This is the primary fix for the ~30% depth
underestimate on real targets. Add a `--quarters` CLI flag to control
how many to download (default: all).

### 3. Phase 4b — transit-masked flattening

In `pipeline/transform.py`, the Savitzky-Golay flatten doesn't know
transit dips are real physics — if the window overlaps a transit, it
partially removes it. The fix is to:

1. Run a quick BLS on the raw (unflattened) light curve to get a
   rough ephemeris
2. Mask out in-transit cadences before calling `flatten()`
3. Interpolate across the masked gaps
4. Then flatten — the filter never sees the transit

`lightkurve` supports this: `lc.flatten(mask=transit_mask)`. The
transit mask is `lc.create_transit_mask(period, transit_time, duration)`.

This removes the systematic depth bias entirely and should bring
real-target results in line with published values.

### 4. Phase 6 — TESS adapter validation

The `--mission TESS` flag is threaded through the CLI and `ingest.py`
already passes it to `lightkurve`. What's needed:
- Test on a known TESS exoplanet (e.g. TOI-132 b, published Rp/R★ ≈ 0.0245)
- TESS cadence is 2 min (short) or 10 min (long) vs Kepler's 29.4 min —
  the BLS period grid and flatten window may need tuning per mission
- Add a `CADENCE_MINUTES` lookup dict in `transform.py` keyed by mission

### 5. Phase 7 full — Wolf-Rayet physics loss

The variability branch in `pipeline/analyze.py` currently runs
Lomb-Scargle and returns period/amplitude/RMS. The Phase 7 extension
is a second PINN mode for stellar variability, with a different physics
loss encoding WR spectral emission-line variability (stochastic wind
modulation, not transit geometry). This is the most research-heavy
remaining task — implement after the archive validation confirms the
transit pipeline is quantitatively correct.

### 6. Streamlit Community Cloud deployment

- Add a `secrets.toml` or environment variable for any API keys (none
  currently needed — MAST is public)
- Replace `sqlite3` local path in `db/storage.py` with an env-variable-
  controlled path so the cloud deployment can point at a bundled
  read-only DB with pre-processed demo targets
- Push to GitHub, connect repo to share.streamlit.io
- The demo DB (3 synthetic targets + Kepler 8-17) should ship with the
  repo so the dashboard works immediately on first visit

### 7. Streamlit KOI range + candidate selectors

Add two dropdowns to the Streamlit dashboard (`app.py`):

1. **Kepler object range selector** — lets the user pick a range of
   Kepler objects (e.g. Kepler-8 through Kepler-17) to load / display
   results for. Mirror the `--range Kepler 8 17` CLI behaviour in the UI.
2. **Candidate KOI selector** — a separate dropdown containing the list
   of KOIs that are *still being analyzed* (confirmation pending /
   candidate status), distinct from the confirmed planets. Source this
   list from the KOI cumulative table (e.g. `koi_disposition = 'CANDIDATE'`
   on the NASA Exoplanet Archive) or a locally tracked "in-progress" set.

## Key design decisions to preserve

- **`method` column in `results` table:** BLS and PINN results live in
  the same table, distinguished by `method='bls'` / `method='pinn'` /
  `method='variability'`. The dashboard compares them without schema
  changes. Do not break this.
- **PINN curves stored as arrays, not model weights:** `save_pinn_profile()`
  writes `pinn_phase` and `pinn_flux` into the target's `.npz`. The
  dashboard serves them without importing torch. Do not change this to
  loading a saved model at serve time.
- **Fourier feature encoding in `pinn.py`:** `FourierFeatures(n_freq=32)`
  is load-bearing — the v1 flat-MLP version plateaued at loss=3.16e-6
  (exactly the MSE of a flat line ignoring the transit). The DEBUGGING
  NOTE in the file documents this. Do not remove the encoder.
- **Lambda warmup in training loop:** `lam=0` for the first 30% of
  epochs, then linear ramp to `lam_max`. Enforcing the geometry
  constraint on an untrained network anchors depth to garbage. The
  warmup is intentional.
- **Star rendering is physics-based, not stock art:** `blackbody_rgb()`
  integrates Planck's law against CIE colour-matching functions. The
  render functions accept `teff` and `stellar_radius` from the FITS
  header. Do not replace with static images.

## Physics reference

**Transit depth:** `Delta F = (Rp / R*)^2`

**PINN loss:**
```
L_total = L_data + lambda * L_geometry + 0.1 * L_baseline
L_data     = MSE(F_pred, F_obs)
L_geometry = (depth_model - depth_param)^2
L_baseline = mean((F_oot - 1)^2)
```

**Stellar colour:** Planck blackbody at Teff integrated against CIE
1931 XYZ colour-matching functions (Wyman, Sloan & Shirley 2013 analytic
fits), converted to sRGB via D65 matrix + gamma.

**Limb darkening:** Linear law `I(mu) = 1 - u * (1 - mu)` with
temperature-interpolated `u` from Claret & Bloemen 2011 tables.
