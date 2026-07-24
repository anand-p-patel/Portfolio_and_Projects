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
> vetting, Wolf-Rayet variability, and JWST/HST spectroscopy — all served
> from the MAST archive — it was renamed accordingly.

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
| Kepler-10 | 0.0300 | 0.0124 | -58.8 | 0.0265 | -11.8 |
| Kepler-11 | 0.0361 | 0.0260 | -27.9 | 0.0498 | +38.2 |
| Kepler-12 | 0.1215 | 0.1183 | -2.7 | 0.1236 | +1.7 |
| Kepler-13 | 0.0648 | 0.0646 | -0.2 | 0.0661 | +2.0 |
| Kepler-14 | 0.0570 | 0.0444 | -22.1 | 0.0493 | -13.5 |
| Kepler-15 | 0.0994 | 0.1006 | +1.2 | 0.1038 | +4.4 |
| Kepler-16 | 0.1194 | 0.1930 | +61.7 | 0.2101 | +76.0 |
| Kepler-17 | 0.1332 | 0.1334 | +0.2 | 0.1398 | +5.0 |

**The headline: on the five geometrically clean, single-transit hosts —
Kepler-8, -12, -13, -15, -17 — the pipeline agrees with published Rp/R* to
a few percent** (BLS mean |Δ| 2.2%, PINN 3.4%; Kepler-13 −0.2%, Kepler-17
+0.2%, Kepler-15 +1.2%, Kepler-12 −2.7%). These are the targets whose
signal actually matches the single-transit model the pipeline assumes, and
there the agreement is quantitative. Every larger deviation in the table
has a specific, identifiable astrophysical cause — none is estimator noise:

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

(Kepler-13 b — a hot Jupiter in a binary — is absent from the archive's
`pscomppars` table, so `validate.py` falls back to the KOI cumulative table
for it; there it validates cleanly at −0.2%, one of the tightest rows in
the table. Its period was one of the three harmonic aliases the next
section corrects: 5.291 d → 1.7636 d.)

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

### Harmonic aliasing — the bug a radius-only check couldn't see

Resolving the period finely is necessary but not sufficient: BLS can pin a
period precisely and still pin the *wrong* one. Box-least-squares power at
an integer harmonic k·P_true rivals the power at the fundamental, and on a
long baseline the coarse grid smears the shorter true period more than the
harmonic — so the search settles on k·P_true. An external code review
prompted a direct check against the archive's published *periods* (not just
radii), and three targets turned out to be exact harmonic aliases:

| Target | Stored period | True period | Alias |
|--------|---------------|-------------|-------|
| Kepler-10 | 5.0250 d | 0.8375 d | 6× |
| Kepler-13 | 5.2908 d | 1.7636 d | 3× |
| Kepler-17 | 2.9714 d | 1.4857 d | 2× |

The matches are exact to parts in 10⁶ (Kepler-13: 3 × 1.763588 = 5.290764
vs stored 5.290761), so these are arithmetic identities, not coincidences.

Why it went unnoticed is the sharpest lesson here: **`validate.py` compared
only Rp/R*, and Rp/R* is nearly blind to a period alias.** At a 2× alias
the even-numbered transits still stack at phase 0 and the box still measures
the right depth, so Kepler-17 reported a −0.9% radius agreement while its
period was a clean factor of two wrong. A validation that checks only the
headline quantity will bless a broken one. `validate.py` now also fetches
`pl_orbper` and reports, per target, the nearest simple-harmonic
relationship (`period_check`) with a fractional residual — a 6× at residual
3e-6 is an alias; Kepler-16's 1/8× at residual 0.52 correctly *declines* to
call anything a match.

**The fix (`run_bls` Stage 3, harmonic disambiguation).** After the
two-stage search finds a peak period P, test each sub-harmonic P/k
(k = 2…8): fold at P and ask whether *every* sub-position j·P/k holds a
real, comparable-depth, significant transit. If they do, the fundamental is
P/k — adopt the smallest such period and re-refine. A correctly-recovered
target fails this at every k (the intermediate phases are empty baseline),
so clean targets are untouched. On the real stored arrays it recovers
Kepler-10 → 0.8375, -13 → 1.7636, -17 → 1.4857 and leaves the other seven
Kepler targets, both TESS targets, and both synthetic demos unchanged.
Kepler-16 is deliberately left at 13.69 d: its signal is the binary's
stellar eclipse and the real circumbinary planet (~229 d) lies outside the
search grid entirely — an alias with no in-grid fundamental to recover,
correctly flagged rather than fabricated. (The validation table above is
post-fix — Kepler-10/13/17 were reprocessed through the corrected search
with `python run_pipeline.py --targets Kepler-10 Kepler-13 Kepler-17 --pinn
--vet`; regenerate it any time with `validate.py --range Kepler 8 17
--markdown`. Note how the `resid` column in a `validate.py` run now reads
~1e-6 at `1x` for all three, versus the clean harmonic ratios they showed
before.)

### The validation harness — a self-test that can fail

The synthetic path used to print truth beside recovered and never compare
them: a harness built to be read, not to fail. `run_pipeline.py --self-test`
now asserts. Per synthetic target it checks recovered vs known truth against
per-quantity tolerances (period 0.5 %, depth 10 %, Rp/R* 5 %, duration one
BLS grid cell), and it adds five stress cases the old demo set never
covered:

- **SYNTH-EB** — an eclipsing binary that *must* be rejected. It has
  unequal odd/even eclipse depths and no visible secondary, so BLS finds its
  true period and the odd/even test condemns it (135σ → `false_positive`).
  It is the positive negative-control: proof the vetting cascade can say
  *no*, not just *candidate*.
- **SYNTH-EB-SEC** — a *symmetric* eclipsing binary (near-equal primary and
  secondary), which is the **most common** real EB morphology. It *should*
  be rejected, but BLS folds it at P/2 — primary and secondary alternate and
  look identical at half the period. The odd/even signal does *not* vanish:
  it survives at ~16σ. It slips through as `candidate` because the depth
  difference is only ~12 % of the depth, below the `ODDEVEN_FRAC_MIN = 0.5`
  fractional gate, which discards it. (Lowering that cut to ~0.10 would
  catch this injection, but a *truly* symmetric EB is genuinely degenerate
  under single-period photometry — separating it needs the secondary test
  evaluated at 2×P, a centroid, or radial velocity. The threshold is
  miscalibrated by ~4×; tightening it narrows the gap, it does not close
  it.) Rather than hide this behind SYNTH-EB's no-secondary shape, the
  harness runs it as an **expected failure (xfail)**: it asserts the
  *desired* `false_positive`, records the miss as a documented known gap,
  and — because the assertion is for the correct behaviour — would flip to a
  loud `XPASS` the day the vetting is fixed. A comment saying a test avoids
  a known failure is a bug report; this is the test.
- **SYNTH-ALIAS** — a 1.3 d transit on a real-Kepler-length (1400 d)
  baseline. The coarse grid smears its fundamental, BLS locks onto the 2×
  harmonic, and the harness asserts on *period* — so it fails on the
  un-fixed search and passes once Stage-3 disambiguation is in. It is the
  regression test for the fix.
- **SYNTH-BIGRP** — a clean but very deep transit (Rp/R* = 0.20, above the
  `MAX_PLANET_RATIO = 0.18` cap) with no odd/even or secondary signature, so
  the radius-ratio cap is the only thing that can reject it. It asserts
  `false_positive` — the regression test for the dual-ratio cap fix, which
  was otherwise exercised only by Kepler-16 on real data.
- **SYNTH-SHALLOW** — a Kepler-10-scale shallow transit (Rp/R* ≈ 0.017). BLS
  recovers it; the transit PINN over-reports its depth (below). The check
  asserts the *PINN* radius matches truth and is an **xfail**, so the bias
  is an executed test, not just prose. It needs torch, so it is **skipped**
  when torch is absent — which keeps the rest of the harness torch-free.

The harness runs entirely in memory, writes nothing to the bundled database,
and exits non-zero on any *unexpected* result — documented gaps (xfail) and
torch-less skips stay green, so it is safe to run in CI:

```bash
python run_pipeline.py --self-test
# → 13/13 checks passed, 1 known gap(s) (xfail), 1 skipped.
# (with torch installed the shallow-PINN skip runs as a second xfail)
```

Runtime: a few seconds without torch; ~2.5 min with it, essentially all of
which is training the one PINN case. Fine locally and for a per-PR gate;
worth splitting out if it ever runs per-commit.

The broader point is the honest one: the original validation wasn't
*absent* — `validate.py` queried a real external archive and printed a MAE
summary — it was too *narrow*, checking one quantity (Rp/R*) on a target set
whose ground-truth members were all geometrically easy. Widening it to check
period, and adding a target that should be rejected and one that should be
un-aliased, is what turns "the pipeline happened to work" into "here is how
I know it works, and here is what it still can't do."

### BLS vs PINN, honestly

With a precisely phased fold, the classical BLS box is hard to beat: on
the clean hosts it matches published to ~1–3%. The PINN's smooth,
physics-constrained profile lands in the same few-percent band on deep
transits and is comparable, not dramatically better. Its reported Rp/R* is
measured off the *fitted profile* — √(1 − mean F_pred) over the in-transit
grid — not the learnable `depth_param`, which only anchors the profile
through `L_geometry`.

**Known limitation (shallow transits).** The PINN carries a roughly additive
depth offset of order ~1e-3 in that profile read-out. On deep transits it is
swamped; on shallow ones it dominates, and the PINN/BLS radius ratio rises
monotonically as depth falls — **2.14×** on Kepler-10 (Rp/R* ≈ 0.012), ~1.9×
on Kepler-11, ~1.7× on TOI-1074.01, down to ~1.0× on the deep hosts. So
**below Rp/R* ≈ 0.05, trust the BLS value, not the PINN.** This is documented
three ways so it cannot be mistaken for a measurement: the `SYNTH-SHALLOW`
harness xfail asserts it, the dashboard's PINN caption says it, and this note
quantifies it. Calibrating the read-out (central-minimum vs profile-average)
is a clean future lever; until then the PINN's worth is its continuous,
geometry-constrained transit model and fitted curve, not a headline accuracy
win over a well-resolved box on shallow signals.

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
- **Radius-ratio cap** — a dip too deep to be a planet (Rp/R* > 0.18) is a
  star. The check reads **both** the BLS box-fit ratio and the ratio
  recomputed from the fold, and fires if *either* exceeds the cap. Reading
  both matters: when the period is an eclipse harmonic the in-transit
  window lands off the true eclipse and the recomputed depth collapses, so
  the box-fit ratio is the one that still tells the truth (Kepler-16: BLS
  0.19 vs recomputed 0.009).
- **Centroid motion** (`--centroid`, needs pixel data) — an in-transit
  shift of the flux centroid means the eclipse is on a different star in
  the aperture: a background-eclipsing-binary blend.

Each test gates on **both** statistical significance **and** relative
size, so a formally-significant but physically negligible effect on a
high-SNR light curve doesn't condemn a real planet. The suite earns its
keep on real data: it passes the clean confirmed planets (Kepler-8, -12,
-13, -15, TOI-132) and flags the problem cases for the right reason —
**TOI-1074.01** (odd 1149 ppm vs even −54 ppm, 19σ → eclipsing binary at
2× the period), and **Kepler-16**, the circumbinary system whose deep
stellar eclipse trips the radius-ratio cap (Rp/R* 0.19 → *false positive*,
correctly — it had previously slipped through as a candidate because the
recomputed depth alone missed it). Detection and *vetting* are different
jobs; this is the second one.

## The physics-informed loss — why it's a PINN, not a black box

A black-box network fitting a transit minimises the data term alone:

    L_data = MSE(F_pred, F_obs)

With enough capacity that finds *a* curve through the points — but nothing
stops it overfitting noise, drifting the baseline, or producing a dip
whose depth means nothing physically. The solution space is unconstrained.

The **transit PINN** (Phase 4) adds two physics penalties:

    L_total    =  L_data  +  λ · L_geometry  +  0.1 · L_baseline

    L_data     =  MSE(F_pred, F_obs)            # fit the photometry
    L_geometry =  ( ΔF_model − depth )²         # geometry law: the model's
                                                #   realised depth must equal an
                                                #   explicit parameter; √depth = Rp/R*
    L_baseline =  mean( (F_oot − 1)² )          # flux conservation: F ≡ 1 out of transit

where `ΔF_model = 1 − mean(F over the transit core)`, `depth` is a
**learnable physical parameter**, and `F_oot` is the model on the
out-of-transit grid.

What the penalties actually do — the difference from a black box:

- **L_baseline** pins the out-of-transit model to exactly 1, so the network
  can't absorb slow drift into the baseline; the only place it can put a
  dip is a real transit.
- **L_geometry** ties the realised depth to an explicit parameter, so depth
  isn't an incidental by-product of the fit but a *constrained, extractable*
  quantity — and `√depth` is directly the radius ratio Rp/R*. A black-box
  net gives you a curve; the PINN gives you a physical number with the
  geometry law `ΔF = (Rp/R*)²` baked in.

The penalties don't touch the weights directly — they reshape the loss
landscape so its minimum sits in the physically-valid region (baseline
conserved, depth = a real parameter), which regularises against noise *and*
makes the physics readable out of the model.

**λ warm-up:** λ = 0 for the first 30% of epochs, then a linear ramp to
λ_max. Enforcing geometry on an untrained network would anchor the depth to
garbage; the data term shapes the curve first, then the physics phases in.

**Fourier-feature input** — phase is lifted into a periodic basis before
the MLP:

    x  →  [ sin(π k x), cos(π k x) ]   for k = 1 … n_freq   (n_freq = 32)

A plain tanh MLP suffers spectral bias and never resolves the narrow (~4%
of the domain) dip — it plateaus at the MSE of a flat line. The Fourier
lift makes the sharp feature a linear combination the network reaches
immediately (Tancik et al. 2020) and respects the fold's periodicity.

**Variability (Phase 7 SHO-PINN)** — the second PINN is informed by the
stochastically-driven damped harmonic oscillator (the celerite SHO), whose
equation of motion defines the physics:

    g'' + (ω₀/Q)·g' + ω₀²·g = 0        (g = f − μ)

The coherence — quality factor **Q** — is read from the SHO's
autocorrelation signature, whose envelope decays at integer-period lags n:

    ACF(nP) ≈ exp(−π n / Q)     ⇒     Q = −π / slope( ln |ACF(nP)| )

(the ODE-residual-in-the-loss form was numerically unstable, so the network
supplies the physics-informed fit and the SHO physics reads Q off its
correlation structure — see the variability section). High Q ⇒ coherent
pulsation; low Q ⇒ stochastic wind.

## Architecture

                     +-- transit ---> ETL detrend -> BLS -> Transit PINN -> Rp/R* -> Vetting -> disposition --+
    MAST light curves|                                                                                        |--> SQLite + .npz --> dashboard
     (Kepler/K2/TESS)+-- variability -> Lomb-Scargle ------> SHO-PINN ----> coherence Q ----------------------+

    MAST spectra (JWST/HST) --> fetch + parse 1D --> wavelength / flux + WR emission lines -------------------> dashboard

The two PINNs (Transit, SHO) and the vetting suite are distinct stages;
JWST/HST spectroscopy is a separate viewer, not a PINN (no model fits a
spectrum here).

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
  installed). The **JWST** and **HST** missions list Wolf-Rayet stars with
  spectra from that facility and show a spectrum-focused view. Also
  multi-target compare and random exploration. The base dashboard imports
  neither torch, lightkurve, nor astroquery.
- `db/catalog.py` — standard-library NASA-archive queries for the full
  mission catalogue (Kepler KOI cumulative table, TESS TOI table),
  returning confirmed hosts and candidates with a status flag; plus the
  curated `WR_STARS` list (literature Teff/radius/period + optional
  JWST/HST spectrum reference). Safe to import in the lightweight dashboard.
- `pipeline/spectra.py` — fetches and parses 1D JWST/HST spectra from
  MAST (astroquery, lazy-imported), bundles them as .npz, and defines the
  Wolf-Rayet emission-line list; `viz.plots.plot_spectrum` renders them
  with unit-aware line markers.
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
`kepler.db`, the `data/processed/*.npz` light-curve arrays, and
`data/spectra/*.npz` JWST/HST spectra, so a fresh clone renders results
(and Wolf-Rayet spectra) immediately — no pipeline run required on first
visit.

- `requirements.txt` is the app-only dependency set (Streamlit, pandas,
  numpy, matplotlib); the cloud build never installs torch, lightkurve,
  or astroquery. The in-app "analyze" / "fetch spectrum" buttons need
  those and so appear only on a local install, not the cloud deploy.
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
- [ ] Calibrate the transit PINN's shallow-depth read-out — diagnose and
      remove the ~1e-3 additive offset in `model_depth` that makes the PINN
      over-report Rp/R* on shallow transits (PINN/BLS rises monotonically as
      depth falls: 2.14× on Kepler-10). First step is a cheap diagnostic:
      scale a synthetic transit's depth down and sweep `n_freq` — if the
      floor tracks `n_freq`, it's Fourier-basis leakage (core narrower than
      the basis can represent); also check the `L_baseline` weight and the
      `depth_param`/`L_geometry` anchor. Currently a documented known
      limitation, asserted by the `SYNTH-SHALLOW` xfail (trust BLS below
      Rp/R* ~ 0.05). Needs the torch env and would reprocess every PINN row.
- [ ] Data-science / classical-ML layer: a scikit-learn supervised
      false-positive classifier (RandomForest/GradientBoosting) trained on
      the pipeline's per-target features vs the archive's dispositions,
      with Precision/Recall/ROC-AUC and feature importances — learning the
      thresholds the Phase 10 vetting suite hand-tunes; plus unsupervised
      anomaly clustering.
- [ ] Expand the JWST/HST catalogs — build a browsable Wolf-Rayet
      spectra list from the VizieR WR catalogue cross-matched against MAST
      (unlike Kepler/TESS, JWST/HST have no ready-made object table).
- [ ] Exoplanet-atmosphere cross-reference — for a transiting planet with
      a JWST/HST transmission spectrum, show the transit fit (size, from
      BLS+PINN) alongside the atmospheric spectrum (composition: H2O/CO2/
      CH4 bands). Unifies the photometry and spectroscopy halves.
- [x] JWST / HST Wolf-Rayet spectral viewer — a separate capability
      (pointed spectroscopy, not light curves; the PINN doesn't apply).
      `pipeline/spectra.py` fetches/parses 1D spectra from MAST (JWST
      EXTRACT1D, HST STIS X1D, HST GHRS paired C0F/C1F). JWST and HST are
      their own missions in the dashboard; 4 spectra ship bundled (WR 140
      JWST dust; WR 136, gamma Vel, EZ CMa HST UV) with WR emission-line
      markers. TODO (minor): JWST IFU cube 1D extraction (WR 137).
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
