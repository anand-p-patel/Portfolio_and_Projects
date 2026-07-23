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
                                HARNESS_TARGETS)
from pipeline.transform import flatten_light_curve
from pipeline.analyze import run_bls
from pipeline.vetting import vet_lightcurve

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
    P/2 where the odd/even signal vanishes, so single-period vetting passes
    it as `candidate`. This documents that KNOWN GAP: the check asserts the
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
    return [("SYNTH-EB-SEC.disposition",
             v["disposition"] == "false_positive",
             f"got {v['disposition']!r}, want 'false_positive'  "
             f"(BLS folded at P={r['period_days']:.3f} = P_true/2; "
             f"odd/even σ={v['oddeven_sigma']:.0f}, no flag fires)")]


def run():
    """
    Run every case; return (rows, n_fail). Each row is
    (label, ok, detail, expect_fail). A row counts toward n_fail when it is
    an unexpected failure (not ok, not expected) OR an unexpected pass
    (ok, but expected to fail — a known gap that has silently closed).
    """
    rows = []
    for name in ("SYNTH-DEMO", "SYNTH-DEMO-B"):
        rows += [(l, o, d, False) for l, o, d in
                 _transit_case(name, DEMO_TARGETS[name])]
    rows += [(l, o, d, False) for l, o, d in _eb_case()]
    rows += [(l, o, d, False) for l, o, d in _alias_case()]
    rows += [(l, o, d, True) for l, o, d in _eb_sec_case()]
    n_fail = sum(1 for _, ok, _, xfail in rows if ok == xfail)
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
    n_xfail = 0
    for label, ok, detail, xfail in rows:
        if xfail:
            mark = "XPASS" if ok else "XFAIL"   # XPASS = a known gap closed
            n_xfail += not ok
        else:
            mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label.ljust(width)}  {detail}")
    total = len(rows)
    hard = total - n_xfail          # checks expected to pass
    summary = f"\n{hard - n_fail}/{hard} checks passed"
    if n_xfail:
        summary += f", {n_xfail} known gap(s) (xfail)"
    print(summary + ".")
    if n_fail:
        print(f"{n_fail} unexpected result(s) — FAILED.")
        sys.exit(1)
    print("All checks passed (known gaps documented).")


if __name__ == "__main__":
    main()
