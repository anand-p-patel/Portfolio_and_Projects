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

**Known systematic (UPDATED — original note below was wrong):** The old
Kepler-8 result (PINN ≈ 0.0719 vs published ≈ 0.096) was NOT flatten
erosion. Root cause, found during Phase 6: (a) a silently-broken
lightkurve BLS grid and (b) period under-resolution smearing the
full-mission fold. Fixed with an astropy two-stage BLS (see task 4).
Current Kepler-8: BLS 0.0915 / PINN 0.0939 vs published 0.0979. Clean
single-transit hosts now agree with published to a few percent. Full
validation table in METHODOLOGY.md.

  (Original note, kept for history: "Single-quarter Savitzky-Golay
  flattening biases transit depth ~2% low ... Fix is Phase 5b + 4b.")

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

### 1. NASA Exoplanet Archive validation table  ✅ DONE

Implemented in `validate.py` (`python validate.py --range Kepler 8 17
[--markdown]`). Queries the archive TAP service, reconstructs published
Rp/R* = (pl_rade·R⊕)/(st_rad·R☉), and tabulates published vs BLS vs PINN
with per-method Δ% and a mean-|Δ| summary. The annotated table is in
METHODOLOGY.md. Original spec below.


Run `--range Kepler 8 17 --pinn`, then fetch published Rp/R★ from the
NASA Exoplanet Archive API for each target and build a comparison table.
The API endpoint is:

```
https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query=select+pl_name,pl_rade,pl_radj,st_rad+from+pscomppars+where+hostname+like+%27Kepler-8%27&format=json
```

Add a `validate.py` script that queries the archive for a list of
target names and prints the comparison table (published vs BLS vs PINN).
This table goes in README.md and is the centrepiece of the portfolio.

### 2. Phase 5b — multi-quarter stitching  ✅ DONE

Implemented: `fetch_light_curve()` now does `download_all().stitch()`
across all quarters, narrowed to one pipeline author + one cadence (see
`_select_products`, refined in task 4) so mixed products aren't stitched
(that had bloated Kepler-8 to 1.45M points; now a clean 65k at 29.4 min).
New `--quarters N` CLI flag (default: all).

NOTE: the improvement numbers first reported here (26.6%→4.8% etc.) were
measured under a broken BLS engine and are SUPERSEDED. Multi-quarter
stitching only pays off together with the two-stage BLS period refine
from task 4 — without it the long-baseline fold smears and reads 30-40%
low. See task 4 and METHODOLOGY.md for the corrected story. Original spec
below.


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

### 3. Phase 4b — transit-masked flattening  ✅ DONE (with a caveat)

Implemented as a two-pass detrend in `process_transit`: unmasked flatten
→ rough BLS ephemeris → `create_transit_mask` (widened 1.3×) → masked
re-flatten → final fit. Default on; `--no-mask-transits` disables it.

IMPORTANT FINDING — the brief's premise was wrong. Transit masking does
NOT fix the real-target depth bias. Verified on synthetic ground truth:
at a narrow flatten window (15) unmasked erodes Rp/R* to −19.9% and the
mask recovers it to −1.2%, BUT at the default ~2-day window (~20× the
transit) masking is a no-op — there is nothing to erode. So the
full-mission Kepler numbers are unchanged by masking (no re-run needed).
UPDATE (task 4): the big ~30% low bias turned out to be period-smearing,
fixed by the two-stage BLS — not box-averaging. What remains on clean
hosts after that fix is only a few % (Kepler-8 box 0.0915, central-min
0.0953, published 0.0979), the small box-vs-limb-darkening gap a
Mandel–Agol model would close. Phase 4b stays valuable as a narrow-window
safeguard. Details in METHODOLOGY.md. Original spec below.


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

### 4. Phase 6 — TESS adapter validation  ✅ DONE

Validated on TOI-132 b (TESS): BLS +5.6%, PINN +26% vs the live archive
value 0.0348 (the brief's 0.0245 was outdated). Delivered:
- Mission-aware product selection (`AUTHOR_PREFERENCE` in ingest.py):
  Kepler→official 1800 s, TESS→120 s SPOC, no mixed-pipeline stitches.
- `CADENCE_MINUTES` + `flatten_window_length()` in transform.py: `--window`
  now auto-scales from the light curve's cadence (Kepler→101, TESS→1483).

TWO BUGS FOUND + FIXED en route (both in analyze.py `run_bls`), and they
also correct the task 2/3 story:
- lightkurve's BLS auto-sizes its period grid to the total time-span and
  HARD-ERRORS on stitched multi-sector TESS data. Rewrote run_bls on
  astropy `BoxLeastSquares` directly.
- A single coarse period grid under-resolves long baselines: a period off
  by one step smears the fold and reads depth 30-40% LOW. This (not
  flatten erosion or box-averaging) was the real source of the earlier
  low bias. Fixed with a TWO-STAGE BLS (coarse global → fine local
  refine). Full-mission clean hosts now within a few %: Kepler-15
  0.060→0.101, Kepler-12 0.083→0.118. NOTE: with a precise BLS the box
  baseline is excellent and the PINN no longer clearly beats it (it
  slightly overshoots on shallow transits) — see METHODOLOGY. Original
  spec below.

The `--mission TESS` flag is threaded through the CLI and `ingest.py`
already passes it to `lightkurve`. What's needed:
- Test on a known TESS exoplanet (e.g. TOI-132 b, published Rp/R★ ≈ 0.0245)
- TESS cadence is 2 min (short) or 10 min (long) vs Kepler's 29.4 min —
  the BLS period grid and flatten window may need tuning per mission
- Add a `CADENCE_MINUTES` lookup dict in `transform.py` keyed by mission

### 5. Phase 7 full — Wolf-Rayet physics loss  ✅ DONE

Built `pipeline/pinn_var.py`: a SHO-PINN for stellar variability. Fits a
smooth physics-informed model of the light curve (Fourier features,
torch-free stored overlay) and derives the damped-oscillator quality
factor Q — the coherence — from the signal's autocorrelation
(Q = −π/slope of ln|ACF(nP)|, the SHO's ACF envelope). Added SYNTH-WR
(incoherent WR-like) target; Q cleanly separates coherent (SYNTH-VAR
Q=88) from stochastic (SYNTH-WR Q=13). Wired: `--mode variability --pinn`,
`quality_factor` DB column, `pinn_var` profile arrays, dashboard Q metric
+ folded overlay + coherence readout.

Dashboard WR mission (added on request): a curated Wolf-Rayet mission
(`db/catalog.WR_STARS`, own mission set) with literature Teff/radius/
period per star (TESS headers give wrong params + periods lose to red
noise). Each shows a physics-simulated hot-blue star portrait; Analyze-now
runs variability mode + SHO-PINN inline. Ships WR 134 (Q≈3) and WR 6/EZ
CMa (Q≈5) analyzed — real WR winds are stochastic, exactly as predicted.
`run_variability` now takes min/max period bounds.

IMPORTANT PIVOT (honest): the literal SHO ODE-residual-in-the-loss (the
approved design) proved numerically unstable — free frequency drifts and
the trivial flat g=0 zeroes the residual, collapsing amplitude. Pivoted
to the mathematically-equivalent SHO autocorrelation (its ACF is
exp(−ω₀τ/2Q)cos ω₀τ), which is robust. The network still provides the
physics-informed fit. Documented in pinn_var.py + METHODOLOGY. Original
spec below.


The variability branch in `pipeline/analyze.py` currently runs
Lomb-Scargle and returns period/amplitude/RMS. The Phase 7 extension
is a second PINN mode for stellar variability, with a different physics
loss encoding WR spectral emission-line variability (stochastic wind
modulation, not transit geometry). This is the most research-heavy
remaining task — implement after the archive validation confirms the
transit pipeline is quantitatively correct.

### 6. Streamlit Community Cloud deployment  ✅ DONE (prep)

Deployment-ready; the actual share.streamlit.io connect is a manual step
for the owner. Delivered:
- `requirements.txt` split into app-only (streamlit/pandas/numpy/
  matplotlib — what the cloud installs) vs `requirements-pipeline.txt`
  (adds lightkurve + torch). The dashboard import tree is torch/
  lightkurve-free, verified.
- `db/storage.py` paths are env-overridable (`KEPLER_DB`,
  `KEPLER_DATA_DIR`) and `.npz` files resolve by basename under the
  current data dir, so the bundled DB's absolute paths from the
  processing machine work on any host.
- `.streamlit/config.toml` dark theme; `.gitignore` keeps the demo DB +
  `.npz` committed but ignores venv/caches/secrets.
- kepler.db + data/processed ship in the repo → dashboard works on first
  visit. Original spec below.


- Add a `secrets.toml` or environment variable for any API keys (none
  currently needed — MAST is public)
- Replace `sqlite3` local path in `db/storage.py` with an env-variable-
  controlled path so the cloud deployment can point at a bundled
  read-only DB with pre-processed demo targets
- Push to GitHub, connect repo to share.streamlit.io
- The demo DB (3 synthetic targets + Kepler 8-17) should ship with the
  repo so the dashboard works immediately on first visit

### 7. Streamlit mission + object selection (with candidate list)  ✅ DONE

Implemented in app.py. A **Mission** selectbox scopes THREE clearly
labelled pickers over the whole archive catalogue
(`db/catalog.fetch_catalog`, cached, offline-graceful): 📊 Analyzed by
local PINN, ✅ Confirmed planets, 🟡 Candidates (still being vetted).
Each picker drives the view via an `on_change` callback; the active
picker syncs to the current target. Selecting an analyzed object → full
diagnostics; selecting an un-analyzed one → archive params + an **Analyze
now** button that runs the pipeline INLINE (lazy-imports lightkurve/torch
so the base app stays light; graceful command fallback on hosted deploys
without them; PINN + quick/1-quarter toggles). Random button fixed via
callback (old body-assignment raised StreamlitAPIException). Verified
end-to-end with Streamlit AppTest incl. a real inline analyze run
(Kepler-20, stored then cleaned up). Original spec below.


Add mission-aware target selection to the Streamlit dashboard (`app.py`).
Scope is broader than just KOIs — the user should be able to pick a
**mission** and then an **object** within it:

1. **Mission selector** — Kepler / K2 / TESS (matching the pipeline's
   `--mission` support). Selecting a mission scopes the object choices
   below to that mission.
2. **Object selector** — pick a specific object (or a range of objects,
   mirroring the `--range` CLI behaviour) within the chosen mission to
   load / display results for.
3. **Candidate selector** — a separate dropdown containing objects that
   are *still being analyzed* (confirmation pending / candidate status),
   distinct from the confirmed planets. For Kepler, source this from the
   KOI cumulative table (`koi_disposition = 'CANDIDATE'`); generalise per
   mission (e.g. TESS TOI candidates) or a locally tracked "in-progress"
   set.

### 8. Vetting / false-positive suite (Phase 10)  ✅ DONE

Built: `pipeline/vetting.py` (odd/even, secondary eclipse, SNR, centroid),
a 4-state disposition (candidate / review / false positive / low SNR),
`--vet` and `--centroid` CLI flags, a `vetting` DB table + save/load, and
a live dashboard "Vetting report" panel (disposition banner + per-test
metrics + flags). Each test gates on significance AND relative size so
high-SNR confirmed planets aren't false-flagged. Backfilled for all
shipped targets. Results: passes clean confirmed planets (Kepler-8/-12/
-15, TOI-132); flags TOI-1074.01 as an EB (odd/even 19σ), and the aliased
Kepler-9/-10/-17 fits. Verified with AppTest + a live centroid run.
Original spec below.

Turn the pipeline from "finds a dip" into "decides whether the dip is a
planet." Standard transit false-positive tests, reported per target and
surfaced in the dashboard (pass/fail + numbers), each stored in the DB:

1. **Odd/even transit consistency** — compare depth of odd- vs
   even-numbered transits. A large difference means the true period is 2×
   (eclipsing binary primary/secondary folded together). PROTOTYPE shows
   this works: TOI-1074.01 fitted at P=6.97 d gave odd=1149 ppm,
   even=−54 ppm (163% diff) → almost certainly an EB at ~13.94 d, not a
   planet. This test is the highest-value one.
2. **Secondary-eclipse check** — look for a dip at phase 0.5. A
   significant secondary flags a self-luminous/stellar companion (EB).
3. **Centroid motion** — needs Target Pixel Files (`lightkurve`
   `search_targetpixelfile`): does the flux centroid shift in-transit? A
   shift means the transit is on a *different* star in the aperture
   (background eclipsing binary / blend). Hardest one — pixel-level data.
4. **Transit SNR threshold** — compute depth·√N_in / σ_oot; gate
   detections at a Kepler-like threshold (~7.1). PROTOTYPE: TOI-1074.01
   SNR ≈ 24.7 (strong signal — but still an EB, which is why SNR alone
   isn't enough and the other tests matter).

Deliverable: a `pipeline/vetting.py` computing these from the stored
light curve + ephemeris, a `vetting` table (or columns), CLI/`--vet`
integration, and a dashboard "Vetting report" panel with a clear
DISPOSITION (planet candidate / likely false positive) and per-test flags.

### 9. JWST / HST Wolf-Rayet spectral data  🚧 IN PROGRESS (day 2 — viewer working)

DAY 2 — SPECTRA VIEWER (done):
- `pipeline/spectra.py`: `parse_spectrum` (JWST EXTRACT1D + HST STIS X1D),
  `_find_x1d` scans multiple observations for a 1D product, `fetch_spectrum`,
  `save_spectrum`/`load_spectrum` (bundled .npz, numpy-only so the
  dashboard imports it clean), `WR_LINES` (UV→mid-IR WR emission lines).
- `viz/plots.plot_spectrum`: wavelength vs flux, unit-aware emission-line
  markers (μm/Å/nm).
- Unified `db.catalog.WR_STARS`: each star may have a TESS light curve
  and/or a `spectrum` {collection, instrument}. Added WR 140 (JWST MIRI
  dust spectrum — showcase) + gamma Vel (HST UV).
- Bundled 3 spectra in `data/spectra/`: WR 140 (JWST MIRI, 3.75-14 um),
  WR 136 (HST STIS/NUV-MAMA UV) and gamma Vel (HST STIS UV). Ship offline.
- Dashboard `render_wr_spectrum`: WR mission stars show a "Spectrum —
  JWST/HST" panel (bundled plot + emission lines, or a Fetch-from-MAST
  button locally). WR 136 shows BOTH TESS variability Q AND its HST
  spectrum. Verified with AppTest.

DAY 2 (cont.) — GHRS done: `_fetch_ghrs` pairs GHRS C0F (wavelength) +
C1F (flux) separate files. EZ CMa bundled: 1531-1567 A, right on the C IV
1550 wind line. Now 4 spectra ship (data/spectra/): WR 140 JWST MIRI, WR
136 + gamma Vel HST STIS, EZ CMa HST GHRS. Three HST instruments parse
(STIS X1D, STIS/NUV-MAMA, GHRS) + JWST EXTRACT1D.

STILL TODO:
- JWST IFU (WR 137): extract 1D from the S3D cube (aperture sum over
  spatial pixels). Deferred — 36 obs, large cube downloads, org-complex;
  low marginal value since WR 140 already showcases JWST. The only WR in
  the catalogue still lacking a working spectrum.
- Optional: flux-normalise / log-y toggle on the spectrum plot.

DAY 1 — DE-RISK + FOUNDATION (done):

A *separate* capability from the light-curve pipeline: JWST/HST are
pointed spectroscopy observatories — MAST/lightkurve return ZERO light
curves for them (verified), and the SHO-PINN needs a time series, so it
can't consume a spectrum. This is a spectral viewer, PINN does NOT apply.

DAY 1 — DE-RISK + FOUNDATION (done):
- Confirmed real WR spectra exist in MAST (via astroquery, already
  installed). Counts: JWST — WR 140 (14, MIRI/SLIT), WR 137 (45,
  NIRSpec+MIRI IFU); HST — WR 6/EZ CMa (11, GHRS), WR 136 (40, STIS),
  gamma Vel (59, STIS/GHRS).
- Built `pipeline/spectra.py`: `find_spectra()` (query, metadata only),
  `parse_spectrum()` (FITS -> wavelength/flux/units), `fetch_spectrum()`
  (download smallest X1D + parse). Verified end-to-end on WR 140 JWST
  MIRI: 385 pts, 3.75-14.0 um, flux in Jy. Curated `WR_SPECTRA` list.
- KEY FORMAT FINDINGS: JWST 1D spectra ('X1D' products) use a standard
  EXTRACT1D binary table (WAVELENGTH um / FLUX Jy) — parses cleanly. HST
  is heterogeneous: STIS/CCD here gave a 2D SX2 (no X1D); GHRS/STIS/FOS
  each differ. JWST IFU (WR 137) gives cubes, needs 1D extraction.

TOMORROW (remaining):
1. HST parsing robustness — handle STIS x1d (SCI ext, per-order 2D),
   GHRS, and IFU 1D extraction; pick products that actually have a 1D
   spectrum. Make `fetch_spectrum` fall back across product types.
2. Spectral plot in `viz/` — wavelength vs flux, log option, and WR
   emission-line markers (He II, C IV, N V, C III — the diagnostic lines).
3. Dashboard viewer — add a "spectrum" panel to the Wolf-Rayet mission:
   for a WR star, a button/tab to fetch & display its JWST/HST spectrum
   alongside the TESS variability. Fetch lazily + cache; ship 1-2
   pre-fetched spectra (e.g. WR 140 JWST) so it works offline on first
   load. Consider a separate `spectra` DB table or bundled .npz.
4. Decide provenance UI: label JWST vs HST + instrument clearly.
   Downloads can be large (esp. IFU) — always filter to X1D, cap size.

### 10. Data-science / classical-ML layer (FUTURE)

Turn this into an explicit ML/data-science project. The pipeline ALREADY
emits a rich per-target feature set and the NASA archive provides
ground-truth labels — a ready-made supervised-learning setup, no new data
collection needed:

- Features per target (already computed, in the DB): BLS period / depth /
  duration / Rp-R*, PINN Rp-R* and quality factor Q, vetting SNR /
  odd-even sigma / secondary / centroid, stellar Teff / radius.
- Labels: the archive's `koi_disposition` (CONFIRMED / FALSE POSITIVE /
  CANDIDATE) — fetch via db.catalog.

Tasks:
1. **Feature engineering** (`ml/features.py`): assemble a feature matrix
   from the DB (one row/target), handle missing values + scaling. This is
   the "stat signal" — documented, principled feature engineering.
2. **Supervised false-positive classifier**: scikit-learn RandomForest /
   GradientBoosting predicting planet vs false-positive from those
   features. Proper held-out split + Precision / Recall / ROC-AUC /
   confusion matrix / feature importances. This is the classic
   exoplanet-vetting ML task (cf. NASA Robovetter; Shallue & Vanderburg
   2018) and would *learn* the thresholds the Phase 10 vetting suite
   currently hand-tunes.
3. **Unsupervised**: cluster targets by derived features to surface
   anomalies / outliers; optionally predict spectral class from Teff.
4. **Dashboard "ML" panel**: predicted disposition + probability per
   target, ROC/PR curves, feature importances. Serve a small fitted-model
   artifact (joblib) so the dashboard stays light — mirror the "PINN
   curves stored as arrays, not weights" pattern. Add scikit-learn to
   requirements-pipeline (NOT the app-only requirements.txt).

Note: the project already IS ML (two PINNs). This adds the classical
supervised/unsupervised layer + the rigorous evaluation metrics (ROC-AUC,
precision/recall, feature importances) that data-science roles look for.

### 11. Expand the JWST / HST spectral catalogs (FUTURE)

Today the JWST/HST missions list only a curated handful of Wolf-Rayet
stars (WR_STARS with a `spectrum` field). Unlike Kepler/TESS — which pull
thousands of objects from purpose-built NASA-archive TAP tables (KOI
cumulative, TOI) — JWST/HST have NO clean object catalogue; their data is
MAST *observations*, so a browsable list must be CONSTRUCTED.

- **11a (quick, ~1 hr)**: hand-expand `WR_STARS` to ~20-40 well-known WR
  stars with JWST/HST programs (research their idents). Bigger list, no
  new infrastructure.
- **11b (full, ~1 session)**: pull the Galactic WR catalogue (van der
  Hucht, ~667 stars) from VizieR (TAP, urllib-able like the NASA archive
  → cloud-OK for browsing), then cross-match each against MAST JWST/HST
  spectroscopy (astroquery, run ONCE offline) to build a small bundled
  *manifest* of WR-stars-with-spectra + instruments. The JWST/HST missions
  then browse that manifest with the same 3-dropdown pattern as
  Kepler/TESS. Caveats: WR-scoped by nature (not "all JWST/HST data");
  displaying a non-bundled spectrum stays local-only (astroquery +
  download), exactly like the "analyze this candidate" flow. Pairs well
  with task 10 (a real stellar catalogue to classify).

### 12. Exoplanet-atmosphere cross-reference (FUTURE) — unify the two halves

The strongest idea: JWST/HST do TRANSMISSION/EMISSION spectroscopy of
exoplanet ATMOSPHERES, and many of those planets are exactly the
transiting planets this pipeline measures photometrically. So for a
transiting planet that also has a JWST/HST atmospheric spectrum, show
BOTH in one view: the transit fit (Rp/R* from BLS + PINN — the planet's
SIZE) alongside the transmission spectrum (molecular absorption:
H2O / CO2 / CH4 / Na / K — the planet's COMPOSITION). This ties the
photometry and spectroscopy halves of the app into one story:
"we measured how big it is; here's what it's made of."

Implementation notes / honest caveats:
- Target overlap: Kepler hosts are mostly too faint for atmospheres;
  the wins are K2/TESS + the classic bright transiters (HD 209458 b,
  WASP-39 b/-96 b, TRAPPIST-1, TOI-270, etc.). Seed a curated list of
  transiting planets with published JWST/HST atmospheric spectra.
- Data is harder than the WR 1D spectra: a *transmission* spectrum is
  transit-depth vs wavelength, a DERIVED product — sometimes in MAST as
  time-series to reduce, sometimes only in the literature / the NASA
  archive's atmospheric tables. Start with a few bundled, pre-reduced
  transmission spectra (wavelength, transit depth) as .npz, plotted with
  molecular-band markers (like WR_LINES).
- Dashboard: on a transit target's page, an "Atmosphere (JWST/HST)" panel
  when a spectrum is available — mirrors the WR spectrum panel. Add an
  atmosphere-flavoured emission/absorption line/band list.

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
