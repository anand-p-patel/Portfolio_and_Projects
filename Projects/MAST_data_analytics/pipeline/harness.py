"""
Validation harness — a self-test that can FAIL.

`run_pipeline.py --synthetic` prints truth beside recovered and never
compares them: a harness built to be read, not to fail. This module adds
the missing assertions. For each synthetic target with known ground truth
it checks recovered-vs-truth against a per-quantity tolerance, and it adds
two stress targets the old demo set never covered:

  * SYNTH-EB    — an eclipsing binary that MUST be rejected (proof the
                  vetting cascade can say "no", not just "candidate").
  * SYNTH-ALIAS — a short-period transit on a real-Kepler-length baseline
                  whose fundamental BLS smears away, locking onto the 2×
                  harmonic. Asserts on PERIOD, so it fails until run_bls
                  gains harmonic disambiguation. This is the regression
                  test for that fix.

Everything runs IN MEMORY. Nothing is written to the bundled database or
data/ arrays — the harness is safe to run in CI and never mutates the
shipped artifacts. Exits non-zero on any failure.

Tolerances (signed off; period relaxed from the first proposal after
testing — see below):
  period_days    0.5% fractional  — real recovery error on these baselines
                 is 0.01–0.1%; the nearest alias is 2× (100% off). 0.5%
                 sits an order of magnitude above the former, two below the
                 latter. (The 1e-4 d absolute first proposed is infeasible:
                 a 30-day baseline only pins the period to ~4e-4 d.)
  depth          10% fractional   — BLS box depth vs box injection differs
                 mainly by duration-grid quantization.
  rp_over_rstar  5% fractional    — = sqrt(depth), half the depth tolerance.
  duration_days  0.05 d absolute  — BLS_DURATIONS is a coarse fixed grid
                 (gaps up to 0.06 d); one grid cell.
"""

import numpy as np

from pipeline.synthetic import (make_synthetic_light_curve, DEMO_TARGETS,
                                HARNESS_TARGETS, injected_quality_factor)
from pipeline.transform import flatten_light_curve
from pipeline.analyze import run_bls
from pipeline.vetting import vet_lightcurve
from pipeline.coherence import coherence_Q, Q_CEIL

TOL = {
    "period_days": ("frac", 5e-3),
    "depth": ("frac", 0.10),
    "rp_over_rstar": ("frac", 0.05),
    "duration_days": ("abs", 0.05),
}


def _check(quantity, recovered, truth):
    """Return (ok, detail) for one recovered-vs-truth comparison."""
    kind, tol = TOL[quantity]
    if recovered is None:
        return False, "recovered=None"
    if kind == "abs":
        err = abs(recovered - truth)
        return err <= tol, f"|Δ|={err:.2e} ≤ {tol:.0e}"
    err = abs(recovered - truth) / abs(truth)
    return err <= tol, f"|Δ|/t={err:.2%} ≤ {tol:.2%}"


def _flatten_bls(lc, mask_transits=True):
    """Mirror process_transit: single flatten -> BLS, then an optional
    transit-masked re-flatten -> BLS so the depth is not eroded."""
    time, flux = flatten_light_curve(lc, window_length=101)
    result = run_bls(time, flux)
    if mask_transits:
        mask = lc.create_transit_mask(period=result["period_days"],
                                      transit_time=result["t0"],
                                      duration=1.3 * result["duration_days"])
        time, flux = flatten_light_curve(lc, window_length=101,
                                         transit_mask=mask)
        result = run_bls(time, flux)
    return time, flux, result


def _transit_case(name, params):
    """Recovered-vs-truth on the four measured quantities."""
    lc = make_synthetic_light_curve(params)
    _, _, r = _flatten_bls(lc)
    truth = {
        "period_days": params["period_days"],
        "depth": params["depth"],
        "rp_over_rstar": float(np.sqrt(params["depth"])),
        "duration_days": params["duration_days"],
    }
    checks = []
    for q in ("period_days", "depth", "rp_over_rstar", "duration_days"):
        ok, detail = _check(q, r.get(q), truth[q])
        checks.append((f"{name}.{q}", ok,
                       f"got {r.get(q):.5g}, truth {truth[q]:.5g}  ({detail})"))
    return checks


def _eb_case():
    """SYNTH-EB must be rejected: disposition false_positive + odd/even flag."""
    params = HARNESS_TARGETS["SYNTH-EB"]
    lc = make_synthetic_light_curve(params)
    time, flux, r = _flatten_bls(lc)
    v = vet_lightcurve(time, flux, r["period_days"], r["t0"],
                       r["duration_days"],
                       bls_rp_over_rstar=r.get("rp_over_rstar"))
    oddeven = any("odd/even" in f for f in v["flags"])
    return [
        ("SYNTH-EB.disposition", v["disposition"] == "false_positive",
         f"got {v['disposition']!r}, want 'false_positive'  "
         f"(BLS P={r['period_days']:.3f})"),
        ("SYNTH-EB.oddeven_flag", oddeven,
         f"odd/even flag {'fired' if oddeven else 'did NOT fire'} "
         f"(σ={v['oddeven_sigma']:.0f})"),
    ]


def _alias_case():
    """SYNTH-ALIAS: period must land on the 1.3 d fundamental, not the 2× alias."""
    params = HARNESS_TARGETS["SYNTH-ALIAS"]
    lc = make_synthetic_light_curve(params)
    _, _, r = _flatten_bls(lc)
    ok, detail = _check("period_days", r["period_days"], params["period_days"])
    return [("SYNTH-ALIAS.period_days", ok,
             f"got {r['period_days']:.4f}, truth {params['period_days']:.4f}  "
             f"({r['period_days'] / params['period_days']:.2f}×)  ({detail})")]


def _eb_sec_case():
    """
    SYNTH-EB-SEC — a symmetric EB (near-equal primary + secondary), the most
    common real EB morphology. It SHOULD be rejected, but BLS folds it at
    P/2, and although the odd/even signal survives (~16σ) the depth
    difference is only ~12 % of the depth — below ODDEVEN_FRAC_MIN = 0.5 —
    so the fractional gate discards it and single-period vetting passes it
    as `candidate`. This documents that KNOWN GAP: the check asserts the
    desired `false_positive`, and run() marks it expect_fail so the miss is
    recorded as an xfail rather than hidden. If the vetting is ever fixed to
    catch it, this flips to XPASS and flags that the gap has closed.
    """
    params = HARNESS_TARGETS["SYNTH-EB-SEC"]
    lc = make_synthetic_light_curve(params)
    time, flux, r = _flatten_bls(lc)
    v = vet_lightcurve(time, flux, r["period_days"], r["t0"],
                       r["duration_days"],
                       bls_rp_over_rstar=r.get("rp_over_rstar"))
    frac = (abs(v["odd_depth"] - v["even_depth"]) / v["depth"]
            if v["depth"] else float("nan"))
    return [("SYNTH-EB-SEC.disposition",
             v["disposition"] == "false_positive",
             f"got {v['disposition']!r}, want 'false_positive'  "
             f"(BLS folded at P={r['period_days']:.3f} = P_true/2; odd/even "
             f"σ={v['oddeven_sigma']:.0f} present but frac={frac:.2f} < "
             f"ODDEVEN_FRAC_MIN 0.5, so discarded)")]


def _bigrp_case():
    """
    SYNTH-BIGRP — a clean but very deep transit (Rp/R* = 0.20, above the
    MAX_PLANET_RATIO = 0.18 cap) with no odd/even or secondary signature, so
    the radius-ratio cap is the only test that can reject it. The regression
    test for the dual-ratio MAX_PLANET_RATIO fix, which was otherwise
    exercised only by Kepler-16 on real data and had no synthetic test.
    """
    params = HARNESS_TARGETS["SYNTH-BIGRP"]
    lc = make_synthetic_light_curve(params)
    time, flux, r = _flatten_bls(lc)
    v = vet_lightcurve(time, flux, r["period_days"], r["t0"],
                       r["duration_days"],
                       bls_rp_over_rstar=r.get("rp_over_rstar"))
    cap = any("too large" in f for f in v["flags"])
    return [
        ("SYNTH-BIGRP.disposition", v["disposition"] == "false_positive",
         f"got {v['disposition']!r}, want 'false_positive'  "
         f"(BLS Rp/R*={r['rp_over_rstar']:.2f} > 0.18)"),
        ("SYNTH-BIGRP.radius_cap", cap,
         f"radius-ratio cap {'fired' if cap else 'did NOT fire'}"),
    ]


def _shallow_pinn_case():
    """
    SYNTH-SHALLOW — a Kepler-10-scale shallow transit. BLS recovers it, but
    the transit PINN over-reports the depth (a ~1e-3 additive offset in its
    profile read-out — negligible when deep, dominant when shallow). The
    check asserts the PINN Rp/R* matches truth and is marked expect_fail, so
    the bias is an executed xfail rather than only a prose caveat. Training
    the PINN needs torch; when torch is absent the case is SKIPPED (ok=None),
    keeping --self-test runnable torch-free.
    """
    label = "SYNTH-SHALLOW.pinn_rp_over_rstar"
    try:
        from pipeline.pinn import train_pinn
    except Exception:
        return [(label, None,
                 "SKIPPED — torch not installed (PINN not exercised)")]
    params = HARNESS_TARGETS["SYNTH-SHALLOW"]
    lc = make_synthetic_light_curve(params)
    time, flux, r = _flatten_bls(lc)
    # Guard the training call too, not just the import: a numerical blow-up
    # or a device problem should report one failed row, not take down the
    # whole harness.
    try:
        pinn_res, _ = train_pinn(time, flux, period=r["period_days"],
                                 t0=r["t0"], duration=r["duration_days"])
    except Exception as exc:
        # Emit an explicit non-xfail row (4-tuple) so a crash is a REAL
        # failure — if it inherited this case's expect_fail it would be
        # silently recorded as the known gap and the suite would stay green.
        return [(label, False,
                 f"PINN training FAILED: {type(exc).__name__}: {exc}", False)]
    truth_rp = float(np.sqrt(params["depth"]))
    ok, detail = _check("rp_over_rstar", pinn_res["rp_over_rstar"], truth_rp)
    return [(label, ok,
             f"PINN got {pinn_res['rp_over_rstar']:.4f}, truth {truth_rp:.4f}  "
             f"({detail})")]


def _coherence_case(n_seeds: int = 12, tol: float = 0.25):
    """
    SYNTH-Q-* — validate the coherence Q against injected ground truth.

    A phase random walk of known step has an exact analytic Q (see
    synthetic.injected_quality_factor), so measured-vs-truth is checkable.
    This is what caught the two estimator systematics in coherence_Q: a
    biased-ACF triangular taper that forced a finite Q on a perfectly
    coherent signal (window-dependent: 90.9 at P=0.85/30 d, 51.0 at
    P=1.3/30 d), and a noise-plateau selection bias that read an injected
    Q of 5 back as 21.

    Averaged over realisations on purpose: the claim under test is that the
    ESTIMATOR is unbiased, which is a statement about the expectation, not
    about one noisy realisation. Fixed seeds keep it deterministic.
    Torch-free and fast — Q never touches the network.
    """
    checks = []
    for name in ("SYNTH-Q-LOW", "SYNTH-Q-MID"):
        base = HARNESS_TARGETS[name]
        truth = injected_quality_factor(base["period_days"],
                                        base["phase_sigma"])
        qs = []
        for k in range(n_seeds):
            p = dict(base, seed=base["seed"] + k)
            lc = make_synthetic_light_curve(p)
            qs.append(coherence_Q(np.asarray(lc.time.value),
                                  np.asarray(lc.flux.value),
                                  p["period_days"]))
        measured = float(np.mean(qs))
        err = abs(measured - truth) / truth
        checks.append((f"{name}.quality_factor", err <= tol,
                       f"mean Q over {n_seeds} seeds = {measured:.1f}, "
                       f"truth {truth:.1f}  (|Δ|/t={err:.1%} ≤ {tol:.0%})"))

    # Coherent control: no decoherence is injected, so the true Q is
    # infinite. Anything well below the ceiling means the estimator's own
    # window is being reported as the star's coherence — the regression
    # test for the biased-ACF taper.
    base = HARNESS_TARGETS["SYNTH-Q-COHERENT"]
    lc = make_synthetic_light_curve(base)
    q = coherence_Q(np.asarray(lc.time.value), np.asarray(lc.flux.value),
                    base["period_days"])
    want = 0.9 * Q_CEIL
    checks.append(("SYNTH-Q-COHERENT.quality_factor", q >= want,
                   f"Q={q:.1f} for a signal with infinite true coherence "
                   f"(want ≥ {want:.0f}; the old biased ACF gave 90.9 here)"))
    return checks


def run():
    """
    Run every case; return (rows, n_fail). Each row is
    (label, ok, detail, expect_fail), where ok is True/False, or None for a
    SKIPPED check (e.g. a PINN case with no torch). A row counts toward
    n_fail when it is an unexpected failure (not ok, not expected) OR an
    unexpected pass (ok, but expected to fail — a known gap that has silently
    closed). Skipped rows never count.
    """
    def tag(checks, default_xfail):
        """Attach expect_fail, letting a case override it per row: a check
        returned as a 4-tuple keeps its own flag (used so a PINN crash is a
        real FAIL, not the case's expected xfail)."""
        return [c if len(c) == 4 else (c[0], c[1], c[2], default_xfail)
                for c in checks]

    rows = []
    for name in ("SYNTH-DEMO", "SYNTH-DEMO-B"):
        rows += tag(_transit_case(name, DEMO_TARGETS[name]), False)
    rows += tag(_eb_case(), False)
    rows += tag(_bigrp_case(), False)
    rows += tag(_alias_case(), False)
    rows += tag(_coherence_case(), False)
    rows += tag(_eb_sec_case(), True)
    rows += tag(_shallow_pinn_case(), True)
    n_fail = sum(1 for _, ok, _, xfail in rows
                 if ok is not None and ok == xfail)
    return rows, n_fail


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print("Validation harness — recovered vs known truth\n")
    rows, n_fail = run()
    width = max(len(label) for label, _, _, _ in rows)
    n_xfail = n_skip = 0
    for label, ok, detail, xfail in rows:
        if ok is None:
            mark = "SKIP"
            n_skip += 1
        elif xfail:
            mark = "XPASS" if ok else "XFAIL"   # XPASS = a known gap closed
            n_xfail += not ok
        else:
            mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label.ljust(width)}  {detail}")
    total = len(rows)
    hard = total - n_xfail - n_skip          # checks expected to pass
    summary = f"\n{hard - n_fail}/{hard} checks passed"
    if n_xfail:
        summary += f", {n_xfail} known gap(s) (xfail)"
    if n_skip:
        summary += f", {n_skip} skipped"
    print(summary + ".")
    if n_fail:
        print(f"{n_fail} unexpected result(s) — FAILED.")
        sys.exit(1)
    print("All checks passed (known gaps documented).")


if __name__ == "__main__":
    main()
