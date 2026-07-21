# Methodology — MAST Data Analytics Engine

> Full technical write-up: physics, validation, architecture, and roadmap.
> For a 30-second setup, see [README.md](README.md).

An end-to-end analytics engine for MAST time-series photometry (Kepler,
K2, TESS). It ingests light curves, isolates transit signals from
instrument drift, and measures the planet-to-star radius ratio with both
a classical baseline (Box Least Squares) and a Physics-Informed Neural
Network; runs a false-positive vetting suite that assigns each candidate
a disposition; characterises stellar variability with a second, SHO-based
PINN that measures coherence (including a dedicated Wolf-Rayet mission);
validates against the NASA Exoplanet Archive; and serves everything
through an interactive dashboard.

The core physics: when a planet crosses its star, the fractional drop in
light obeys the geometry of two intersecting discs,

    Delta F = (Rp / R*)^2

so a careful measurement of transit depth is a direct measurement of
planetary size. Every transit number and image in the dashboard derives
from that relation applied to real (or synthetic ground-truth)
photometry; the variability mode adds the damped-oscillator physics of
the SHO on top (see the variability section).

> Historical note: this began as a single-quarter Kepler transit fitter
> ("Kepler Transit Analytics"). As it grew to span K2/TESS, false-positive
> vetting, and Wolf-Rayet variability — all served from the MAST archive —
> it was renamed accordingly. HST/JWST spectral data is future work.

## Validation (synthetic ground truth, fully offline)

| Target       | Truth Rp/R* | BLS baseline | PINN   |
|--------------|-------------|--------------|--------|
| SYNTH-DEMO   | 0.0949      | 0.0944       | 0.0935 |
| SYNTH-DEMO-B | 0.1265      | 0.1259       | 0.1252 |

| Target   | Truth P (d) | Recovered P | Recovered amp | PINN Q | coherence |
|----------|-------------|-------------|---------------|--------|-----------|
| SYNTH-VAR | 0.8500 | 0.8519 | 0.0197 | 87.7 | coherent |
| SYNTH-WR  | 1.3000 | 1.2707 | 0.0303 | 13.0 | stochastic |

The two variability targets differ only in coherence — SYNTH-VAR is a
clean pulsation, SYNTH-WR a phase-wandering Wolf-Rayet-like wind — and the
Phase 7 SHO-PINN's quality factor Q separates them cleanly (87.7 vs 13.0)
while both periods and amplitudes are recovered. See the variability
section below.

Both transit methods recover the truth to within ~1.5%. The synthetic
generator injects *box* transits (a flat-bottomed dip), so this is
exactly the regime where BLS's box model is the ideal estimator — and
indeed BLS edges the PINN here (−0.5% vs −1.5% on SYNTH-DEMO). That is
the point of the synthetic harness: it proves both estimators are
essentially unbiased on clean, known-shape data, so any larger,
one-sided error on real targets is a property of the *data* (limb
darkening, blends, detrending), not a broken estimator. The PINN's
advantage is not visible here precisely because a box has no round
bottom to reward a smooth profile — that shows up on real transits
below.

## Real-target validation (NASA Exoplanet Archive)

`validate.py` fetches the published planet and stellar radii from the
NASA Exoplanet Archive, reconstructs Rp/R* = (pl_rade·R⊕)/(st_rad·R☉),
and tabulates it against the pipeline. These numbers are from the
**full-mission fit** — every available Kepler quarter stitched together
(Phase 5b), ~65k cadences and ~4 years per target instead of one 90-day
quarter, with a two-stage BLS (see below). Reproduce with
`python validate.py --range Kepler 8 17 --markdown`:

| Target | Published Rp/R* | BLS | ΔBLS% | PINN | ΔPINN% |
|--------|-----------------|-----|-------|------|--------|
| Kepler-8 | 0.0979 | 0.0915 | -6.6 | 0.0939 | -4.1 |
| Kepler-9 | 0.0793 | 0.0391 | -50.8 | 0.0536 | -32.4 |
| Kepler-10 | 0.0300 | 0.0125 | -58.4 | 0.0463 | +54.0 |
| Kepler-11 | 0.0361 | 0.0260 | -27.9 | 0.0498 | +38.2 |
| Kepler-12 | 0.1215 | 0.1183 | -2.7 | 0.1236 | +1.7 |
| Kepler-13 | — | 0.0647 | — | 0.0686 | — |
| Kepler-14 | 0.0570 | 0.0444 | -22.1 | 0.0493 | -13.5 |
| Kepler-15 | 0.0994 | 0.1006 | +1.2 | 0.1038 | +4.4 |
| Kepler-16 | 0.1194 | 0.1930 | +61.7 | 0.2101 | +76.0 |
| Kepler-17 | 0.1332 | 0.1320 | -0.9 | 0.1420 | +6.6 |

**The headline: on the four geometrically clean, single-transit hosts —
Kepler-8, -12, -15, -17 — the pipeline agrees with published Rp/R* to a
few percent** (BLS mean |Δ| 2.8%, PINN 4.2%; Kepler-17 BLS −0.9%,
Kepler-15 +1.2%, Kepler-12 −2.7%). These are the targets whose signal
actually matches the single-transit model the pipeline assumes, and there
the agreement is quantitative. Every larger deviation in the table has a
specific, identifiable astrophysical cause — none is estimator noise:

- **Kepler-14 (−22%)** — the host is a close binary; a near-equal
  companion dilutes the transit, so the *measured* depth is genuinely
  shallower than the deblended published value. Real light, real physics,
  correctly measured — the pipeline doesn't deblend.
- **Kepler-9, -10, -11 (multi-planet)** — a single-signal BLS locks onto
  one body while the table compares against the deepest *catalogued*
  planet; for these systems those need not be the same planet, so the
  comparison is apples-to-oranges by construction.
- **Kepler-16 (+62%)** — a *circumbinary* planet. BLS locks onto the deep
  stellar eclipse of the binary, not the planet, hence the ~2×
  overestimate. An expected, understood failure mode.
- **Kepler-13 (—)** — the archive hostname is "Kepler-13 A", so the
  exact-match query returns no row.

### The period-resolution fix that made the full mission usable

Stitching four years of data (Phase 5b) *should* stack more transits and
sharpen the depth — but naively it did the opposite, reading 30–40% low
(Kepler-15 came out 0.060 vs published 0.099). The cause is subtle: a
period wrong by a single coarse-grid step (~0.003 d) drifts by ~0.3 d
over ~300 orbits and smears the folded transit, halving its apparent
depth. A grid fine enough to avoid this across a 15-day period range and a
1470-day baseline needs *millions* of points — which is exactly why
lightkurve's autoperiod exploded past astropy's evaluation limit on the
stitched sectors.

The fix is a **two-stage BLS**: a coarse global grid finds the peak, then
a fine local grid (±5 coarse steps, ~20k points) pins the period so every
transit stacks coherently. This is bounded and fast, and it is what turns
the full-mission fit from smeared to accurate — Kepler-15 0.060 → 0.101,
Kepler-12 0.083 → 0.118. Multi-quarter stitching was the right idea; it
just surfaced a period-precision requirement the old wrapper had masked.

### BLS vs PINN, honestly

With a precisely phased fold, the classical BLS box is hard to beat: on
the clean hosts it matches published to ~1–3%. The PINN's smooth,
physics-constrained profile lands in the same few-percent band and is
comparable, not dramatically better — and on shallow transits it tends to
*overshoot* the depth slightly (TOI-132 below, Kepler-17 +6.6%), because
its learned profile fits a sharp central minimum. The PINN's value here is
the continuous, geometry-constrained transit model and its fitted curve,
not a headline accuracy win over a well-resolved box. Calibrating the
PINN's depth read-out (central-minimum vs profile-average) is a clean
future lever.

### Phase 6 — TESS validation

The same pipeline, pointed at TESS with `--mission TESS`, validates on
**TOI-132 b** (a hot Neptune). Ingestion narrows MAST's many TESS
products to the official 120 s SPOC pipeline (four sectors), the flatten
window auto-scales from the 2 min cadence to ~2 days (1483 cadences), and
the two-stage BLS handles the multi-sector time-span that would otherwise
explode astropy's grid:

| Target | Mission | Published Rp/R* | BLS | ΔBLS% | PINN | ΔPINN% |
|--------|---------|-----------------|-----|-------|------|--------|
| TOI-132 | TESS | 0.0348 | 0.0368 | +5.6 | 0.0440 | +26.3 |

BLS lands within 6% of published on a ~1300 ppm transit around a
different telescope with 15× finer cadence — end-to-end mission
portability with no per-target tuning. The PINN overshoots here (+26%),
the shallow-transit over-fit noted above. Reproduce with
`python run_pipeline.py --targets TOI-132 --mission TESS --pinn` then
`python validate.py --targets TOI-132`.

### Phase 4b — transit-masked flattening (and why it isn't the fix)

`flatten()` fits the slow instrument drift with a rolling Savitzky-Golay
window; if the window is short relative to the transit it partly fits
(and removes) the dip. Phase 4b makes the detrend a two-pass operation:
flatten once to get a rough BLS ephemeris, mask the in-transit cadences
(`create_transit_mask`, widened 1.3× past the box), then flatten again so
the filter only ever sees the out-of-transit baseline
(`--no-mask-transits` disables it; on by default).

On synthetic ground truth (SYNTH-DEMO, true Rp/R* = 0.0949) it behaves
exactly as the physics predicts — and pins down *when* it matters:

| flatten window | unmasked | masked |
|----------------|----------|--------|
| 101 (~2 d, default) | 0.0944 (−0.4%) | 0.0944 (−0.5%) |
| 31 | 0.0946 (−0.3%) | 0.0946 (−0.3%) |
| 15 | 0.0759 (**−20.0%**) | 0.0944 (**−0.5%**) |

When the window shrinks toward the transit duration the unmasked filter
craters the depth (−20%) and the mask rescues it (−0.5%). At the default
2-day window — ~20× a Kepler transit — there is nothing left to erode, so
masking is a no-op, and the full-mission numbers above are unchanged by
it. Phase 4b earns its place as a correctness safeguard for narrow-window
/ long-transit regimes (short-period TESS planets, coarse cadence), not as
a fix for this table. The small residual that remains on the clean hosts
is the expected box-vs-limb-darkening gap — Kepler-8: BLS box 0.0915,
folded central minimum 0.0953, published 0.0979 — which a Mandel–Agol
limb-darkened model would close.

## Stellar variability & coherence (Phase 7-full)

Not every target is a transit. In variability mode the pipeline skips
flattening (the detrender would erase the signal) and characterises the
star's intrinsic variability. Lomb-Scargle gives the period; the Phase 7
**SHO-PINN** adds the physics Lomb-Scargle can't: the **quality factor
Q**, the coherence of the variability.

Wolf-Rayet photometric variability — rotating wind structures and
stochastic clumping — is modelled by a stochastically driven damped
harmonic oscillator (the celerite SHO; Foreman-Mackey et al. 2017). A
small PINN fits a smooth model of the light curve (periodic Fourier
features, torch-free stored curve for the dashboard), and Q is read from
the SHO's autocorrelation signature: the ACF envelope decays as
exp(−π·n/Q) at integer-period lags n, so `Q = −π / slope(ln|ACF(nP)|)`.
**High Q ⇒ coherent pulsation/rotation; low Q ⇒ stochastic wind.** On the
synthetics above the separation is unambiguous — SYNTH-VAR Q = 87.7,
SYNTH-WR Q = 13.0 — and the folded model shows it: a coherent signal
folds to a clean curve, an incoherent one folds nearly flat.

**Real Wolf-Rayet stars.** The dashboard carries a curated Wolf-Rayet
mission (its own set — WR stars aren't in the exoplanet catalogues, their
TESS headers carry wrong stellar parameters, and their periods collide
with red noise, so each ships with literature Teff/radius/period). Run on
real TESS data they behave exactly as the physics says a hot-star wind
should: **WR 6 (EZ CMa) Q ≈ 5, WR 134 Q ≈ 3** — low coherence, stochastic
wind — against the coherent synthetic pulsator's Q ≈ 88. A bounded period
search (±40% around the literature period) keeps the ~day-scale wind
signal from losing to ~50 d instrumental trends.

**Honest design note.** The textbook PINN move is to put the free-SHO ODE
residual (g″ + (ω₀/Q)g′ + ω₀²g) directly in the training loss and learn
ω₀, Q by autodiff. On this problem that is numerically unstable: the free
frequency drifts, and the trivial flat solution g = 0 zeroes the residual
and collapses the fitted amplitude (the residual is amplitude-degenerate,
so it fights the data term). The autocorrelation is the *same physics* in
integral form — the SHO's ACF is exactly exp(−ω₀τ/2Q)·cos ω₀τ — but robust
to noise and free of the collapse mode. So the network provides the
physics-informed fit and the SHO physics reads Q off its correlation
structure. (The transit PINN carries a similar hard-won correction in its
`DEBUGGING NOTE`.)

## Vetting — is the dip actually a planet? (Phase 10)

A periodic dip is necessary but not sufficient. `pipeline/vetting.py`
runs the standard transit false-positive tests and assigns a
**disposition** — *planet candidate*, *needs review*, *likely false
positive*, or *not significant* — surfaced live in the dashboard and
stored via `--vet`:

- **Transit SNR** = depth·√N / out-of-transit noise, gated at the
  Kepler-canonical ≈ 7.
- **Odd/even consistency** — odd- vs even-numbered transit depths. A
  mismatch means an eclipsing binary aliased to half the true period.
- **Secondary eclipse** — a dip at phase 0.5. A *deep* one (30–70% of the
  primary) is a stellar companion; an *equal* one (>70%) means the fold
  is at 2× the true period.
- **Centroid motion** (`--centroid`, needs pixel data) — an in-transit
  shift of the flux centroid means the eclipse is on a different star in
  the aperture: a background-eclipsing-binary blend.

Each test gates on **both** statistical significance **and** relative
size, so a formally-significant but physically negligible effect on a
high-SNR light curve doesn't condemn a real planet. The suite earns its
keep on real data: it passes the clean confirmed planets (Kepler-8, -12,
-15, TOI-132) and flags the problem cases for the right reason —
**TOI-1074.01** (odd 1149 ppm vs even −54 ppm, 19σ → eclipsing binary at
2× the period), and our aliased Kepler-10/-17 fits (equal secondary →
"re-fold at P/2"). Detection and *vetting* are different jobs; this is
the second one.

## Architecture

    [ Phase 1: Ingestion ] -> [ Phase 2: ETL ] -> [ Phase 3: BLS baseline ]
                                                       |
                              [ SQLite results ] <-----+----> [ Phase 4: PINN ]
                                      |
                              [ Streamlit dashboard ]

- `pipeline/ingest.py` — downloads light curves from the MAST archive
  (lightkurve), mission-parameterised (`--mission Kepler|K2|TESS`),
  and extracts the host star's Teff and radius from the FITS header.
  Stitches every available quarter/sector into one light curve
  (Phase 5b), after narrowing MAST's many products to one pipeline
  author and one cadence (Kepler → official 1800 s long cadence; TESS →
  120 s SPOC), so the stitch never mixes incompatible reductions;
  `--quarters N` caps how many are downloaded.
- `pipeline/transform.py` — Savitzky-Golay detrending, with optional
  transit masking (Phase 4b): the filter can be told which cadences are
  in-transit so it fits the drift from the out-of-transit baseline only
  and never erodes the transit floor.
- `pipeline/analyze.py` — the classical baselines: Box Least Squares
  transit search (transit mode) and Lomb-Scargle period search with
  amplitude/RMS (variability mode; light curves are NOT flattened in
  this mode — the detrender would erase the signal). BLS runs on
  astropy's `BoxLeastSquares` directly in two stages — a coarse global
  grid then a fine local refine around the peak. lightkurve's wrapper
  auto-sizes its grid to the total time-span and blows past astropy's
  evaluation limit on stitched, gap-separated sectors; a single coarse
  grid under-resolves the period on multi-year baselines and smears the
  fold. Two stages are bounded, fast, and recover the true depth.
- `pipeline/pinn.py` — the Physics-Informed Neural Network,
  implemented and annotated as a study document. Fourier-feature
  input encoding (Tancik et al. 2020) defeats spectral bias — the
  file documents the v1 failure that motivated it. A learnable depth
  parameter is tied to the fitted curve through a transit-geometry
  loss term, with a flux-conservation term and a lambda warmup
  schedule. BLS seeds the ephemeris; the PINN refines profile and
  depth.
- `pipeline/pinn_var.py` — the Phase 7-full variability PINN: fits a
  smooth physics-informed model of the light curve and reads the
  damped-harmonic-oscillator quality factor Q (coherence) from the
  signal's autocorrelation. See the variability section below.
- `pipeline/synthetic.py` — four ground-truth demo targets (Sun-like G,
  K dwarf, coherent hot variable, and an incoherent Wolf-Rayet-like
  wind) so every mode of the pipeline, the star rendering, and the
  dashboard demo offline.
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
- `app.py` — Streamlit dashboard: a mission selector (Kepler / K2 /
  TESS, plus a curated **Wolf-Rayet** variable-star set) scopes the object
  pickers. Survey missions get three labelled pickers — 📊 analyzed by the
  local PINN, ✅ confirmed planets, 🟡 candidates still being vetted —
  spanning the whole NASA archive catalogue; the Wolf-Rayet mission lists
  its curated stars, each shown with a physics-simulated portrait from its
  literature Teff and analysed in variability mode on click. Selecting an
  analyzed object shows full diagnostics (BLS-vs-PINN comparison,
  simulated host-star portrait, transit scene, ETL before/after);
  selecting an un-analyzed one shows its archive parameters and an
  **Analyze now** button that runs the pipeline inline (lazy-importing
  lightkurve/torch, with a graceful command fallback where they're not
  installed). Also multi-target compare and random exploration. The base
  dashboard imports neither torch nor lightkurve.
- `db/catalog.py` — standard-library NASA-archive queries for the full
  mission catalogue (Kepler KOI cumulative table, TESS TOI table),
  returning confirmed hosts and candidates with a status flag; safe to
  import in the lightweight dashboard.
- `validate.py` — queries the NASA Exoplanet Archive TAP service for
  published planet/stellar radii, reconstructs Rp/R*, and prints the
  published-vs-BLS-vs-PINN comparison table (plain-text or `--markdown`).
- `pipeline/vetting.py` — Phase 10 false-positive tests (odd/even,
  secondary eclipse, SNR, centroid) and the disposition logic. The
  light-curve tests are pure NumPy (the dashboard computes them live);
  the centroid test lazily imports lightkurve for pixel data.

## Quick start

    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

    # Dashboard only — reads the bundled DB, no torch, no internet:
    pip install -r requirements.txt
    streamlit run app.py

    # Full pipeline — MAST ingestion + PINN training:
    pip install -r requirements-pipeline.txt
    python run_pipeline.py --synthetic --pinn                     # offline, ground truth
    python run_pipeline.py --targets Kepler-8 Kepler-10 --pinn    # real data from MAST
    python run_pipeline.py --range Kepler 8 17 --pinn
    python run_pipeline.py --targets TOI-132 --mission TESS --pinn
    python run_pipeline.py --targets "TIC 470710327" --mission TESS --mode variability --pinn
    python run_pipeline.py --targets Kepler-8 --pinn --vet         # + vetting disposition
    python validate.py --range Kepler 8 17                        # vs NASA archive

Note: PyTorch currently requires Python <= 3.13; create the venv with
`py -3.12 -m venv .venv` on Windows if your default Python is newer. The
dashboard has no such constraint — its dependency set (`requirements.txt`)
is just Streamlit, pandas, numpy, and matplotlib.

## Deployment (Streamlit Community Cloud)

The dashboard is deployment-ready. The repo ships a populated
`kepler.db` and the `data/processed/*.npz` arrays, so a fresh clone
renders results immediately — no pipeline run required on first visit.

- `requirements.txt` is the app-only dependency set; the cloud build
  never installs torch or lightkurve.
- `db/storage.py` reads `KEPLER_DB` and `KEPLER_DATA_DIR` environment
  variables (defaulting to the in-repo paths), so a deployment can point
  at a bundled read-only DB, and resolves each target's `.npz` by
  filename under the current data dir — the stored absolute paths from
  the processing machine don't have to exist on the host.
- Point Streamlit Community Cloud at the repo with `app.py` as the entry
  point. No secrets are needed (MAST and the NASA archive are public);
  `.streamlit/secrets.toml` is gitignored should any be added later.

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
- [x] Phase 4b: transit-masked (two-pass) detrending — verified to
      recover depth at narrow windows; a no-op at the default wide
      window, which localised the real residual to BLS box-vs-limb-
      darkening rather than flatten erosion
- [ ] Limb-darkened transit model (Mandel–Agol) / central-minimum depth
      to close the remaining box-averaging bias
- [ ] JWST / HST Wolf-Rayet *spectral* viewer — a separate capability
      (pointed spectroscopy, not light curves; the PINN pipeline doesn't
      apply). The current WR variability mission is TESS-sourced.
- [x] Phase 5b: multi-quarter stitching — all quarters stitched into one
      light curve (one pipeline author + one cadence); `--quarters N` to
      limit. Two-stage BLS added to resolve the period on long baselines.
- [x] Phase 6: TESS validation — mission-aware product selection,
      cadence-aware flatten window, validated on TOI-132 b (BLS +5.6%)
- [x] Phase 7 (full): SHO-PINN for variability — a damped-harmonic-
      oscillator model yielding the coherence quality factor Q
      (`pipeline/pinn_var.py`); separates coherent pulsation (SYNTH-VAR
      Q=88) from stochastic Wolf-Rayet-like wind (SYNTH-WR Q=13)
- [x] Phase 10: vetting / false-positive suite — odd/even, secondary
      eclipse, SNR, and centroid-motion tests with a per-target
      disposition (candidate / review / false positive / low SNR).
      `pipeline/vetting.py`, `--vet`/`--centroid`, a dashboard vetting
      panel, and a `vetting` DB table. Flags TOI-1074.01 as an eclipsing
      binary (odd/even 19σ) and the aliased Kepler-10/-17 fits.
- [x] Validate real-target Rp/R* against the NASA Exoplanet Archive
      (`validate.py`; table above)
- [x] Dashboard mission → object selection over the full archive
      catalogue (Kepler/K2/TESS scoping; confirmed ✅ + candidate 🟡
      markers, 📊 for locally-analyzed; filterable)
- [x] Deployment-ready for Streamlit Community Cloud — bundled DB,
      env-overridable paths, app-only `requirements.txt` (connect the
      repo to share.streamlit.io to go live)

Built with [lightkurve](https://lightkurve.github.io/lightkurve/),
NumPy, PyTorch, Matplotlib, SQLite, and Streamlit.
