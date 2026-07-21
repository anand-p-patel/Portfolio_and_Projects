"""
Batch pipeline runner (Phase 5 — user-supplied targets).

Usage
-----
Real transit targets (needs internet, hits the MAST archive):
    python run_pipeline.py --targets Kepler-8 Kepler-10 Kepler-17
    python run_pipeline.py --range Kepler 8 12       # Kepler-8 .. -12

With the Phase 4 PINN (requires torch; Python <= 3.13):
    python run_pipeline.py --targets Kepler-8 --pinn

Variability mode (Phase 7 baseline — skips flattening, runs
Lomb-Scargle instead of BLS; for variable stars, e.g. on TESS):
    python run_pipeline.py --targets "TIC 470710327" --mission TESS --mode variability

Offline demo targets with known ground truth (no internet needed):
    python run_pipeline.py --synthetic --pinn
"""

import argparse
import sys

import numpy as np

from pipeline.ingest import fetch_light_curve, get_stellar_params
from pipeline.transform import (flatten_light_curve, flatten_window_length,
                                measure_cadence_minutes)
from pipeline.analyze import run_bls, run_variability
from pipeline.synthetic import make_synthetic_light_curve, DEMO_TARGETS
from db import storage


def expand_range(prefix: str, start: int, end: int):
    """'Kepler', 8, 12 -> ['Kepler-8', ..., 'Kepler-12']"""
    if end < start:
        start, end = end, start
    return [f"{prefix}-{i}" for i in range(start, end + 1)]


def vet_target(target_id, mission, time, flux, result, run_centroid=False):
    """Run the Phase 10 vetting tests and store the report."""
    from pipeline.vetting import (vet_lightcurve, vet_centroid,
                                  DISPOSITION_LABEL)
    vet = vet_lightcurve(time, flux, result["period_days"],
                         result["t0"], result["duration_days"])
    if run_centroid:
        c = vet_centroid(target_id, mission, result["period_days"],
                         result["t0"], result["duration_days"])
        vet["centroid_shift_pixels"] = c.get("centroid_shift_pixels")
        vet["centroid_sigma"] = c.get("centroid_sigma")
        vet["centroid_note"] = c.get("note")
        if c.get("centroid_pass") is False:
            vet["flags"].append(c.get("note", "centroid shift detected"))
            if vet["disposition"] in ("candidate", "review"):
                vet["disposition"] = "false_positive"
    storage.save_vetting(target_id, vet)
    line = f"  vetting: {DISPOSITION_LABEL[vet['disposition']]}"
    if vet["flags"]:
        line += f" — {vet['flags'][0]}"
    print(line)
    return vet


def process_transit(target_id, mission, lc, window,
                    teff=None, stellar_radius=None, use_pinn=False,
                    mask_transits=True, vet=False, run_centroid=False):
    """
    Transit path: flatten -> BLS -> (optional PINN) -> storage.

    Phase 4b (mask_transits=True): a two-pass detrend. Pass 1 flattens
    normally and runs BLS to get a rough ephemeris. Pass 2 masks the
    in-transit cadences from that ephemeris and flattens again, so the
    Savitzky-Golay filter fits the drift from the out-of-transit baseline
    only and never erodes the transit floor. The final BLS/PINN run on
    this bias-corrected flux.
    """
    raw_time = np.asarray(lc.time.value, dtype=float)
    raw_flux = np.asarray(lc.flux.value, dtype=float)

    # A cadence count of 101 is only ~2 days at Kepler's 29.4 min
    # sampling; derive it from the actual cadence so TESS (2 min) gets a
    # physically equivalent window instead of a 3 h one that eats the
    # transit. --window overrides this per run.
    if window is None:
        window = flatten_window_length(lc, mission)
        cadence = measure_cadence_minutes(lc, mission)
        print(f"  cadence {cadence:.1f} min -> flatten window {window} "
              f"cadences (~{window * cadence / 1440:.2f} d)")

    time, flux = flatten_light_curve(lc, window_length=window)
    result = run_bls(time, flux)

    if mask_transits:
        # Widen the mask past the BLS box duration so ingress/egress are
        # protected too, then re-flatten and re-fit on the masked trend.
        transit_mask = lc.create_transit_mask(
            period=result["period_days"],
            transit_time=result["t0"],
            duration=1.3 * result["duration_days"],
        )
        time, flux = flatten_light_curve(lc, window_length=window,
                                         transit_mask=transit_mask)
        result = run_bls(time, flux)

    storage.save_target(target_id, mission, raw_time, raw_flux, time, flux,
                        teff=teff, stellar_radius=stellar_radius)
    storage.save_result(target_id, result)

    if vet:
        vet_target(target_id, mission, time, flux, result,
                   run_centroid=run_centroid)

    pinn_result = None
    if use_pinn:
        # Import here so the pipeline runs without torch installed
        # unless the PINN is actually requested.
        from pipeline.pinn import train_pinn
        print("  training PINN...")
        pinn_result, (phase_days, flux_model) = train_pinn(
            time, flux,
            period=result["period_days"], t0=result["t0"],
            duration=result["duration_days"],
        )
        storage.save_result(target_id, pinn_result)
        storage.save_pinn_profile(target_id, phase_days, flux_model)
    return result, pinn_result


def process_variability(target_id, mission, lc,
                        teff=None, stellar_radius=None, use_pinn=False,
                        period_hint=None):
    """
    Variability path: normalize (NO flatten) -> Lomb-Scargle, and
    optionally the Phase 7-full SHO-PINN (period + coherence Q).

    period_hint (days), when given (e.g. a curated Wolf-Rayet star's
    literature period), bounds the Lomb-Scargle search to ±40% around it
    so red noise / instrumental trends don't win the periodogram.
    Returns (ls_result, pinn_result); pinn_result is None without --pinn.
    """
    raw_time = np.asarray(lc.time.value, dtype=float)
    raw_flux = np.asarray(lc.flux.value, dtype=float)

    norm = lc.normalize()
    time = np.asarray(norm.time.value, dtype=float)
    flux = np.asarray(norm.flux.value, dtype=float)

    if period_hint:
        result = run_variability(time, flux, min_period=period_hint / 1.4,
                                 max_period=period_hint * 1.4)
    else:
        result = run_variability(time, flux)
    storage.save_target(target_id, mission, raw_time, raw_flux, time, flux,
                        teff=teff, stellar_radius=stellar_radius)
    storage.save_result(target_id, result)

    pinn_result = None
    if use_pinn:
        # Lazy torch import — only when the variability PINN is requested.
        from pipeline.pinn_var import train_pinn_var
        print("  training variability PINN (SHO coherence)...")
        pinn_result, (phase_days, flux_model) = train_pinn_var(
            time, flux, period=result["period_days"], verbose=False)
        storage.save_result(target_id, pinn_result)
        storage.save_pinn_profile(target_id, phase_days, flux_model,
                                  prefix="pinn_var")
    return result, pinn_result


def main():
    parser = argparse.ArgumentParser(description="Kepler PINN pipeline")
    parser.add_argument("--targets", nargs="*", default=[],
                        help="Target names, e.g. Kepler-8 Kepler-10")
    parser.add_argument("--range", nargs=3, metavar=("PREFIX", "START", "END"),
                        help="Numeric target range, e.g. --range Kepler 8 12")
    parser.add_argument("--mission", default="Kepler",
                        help="Kepler, K2, or TESS (Phase 6 adapter)")
    parser.add_argument("--mode", choices=["transit", "variability"],
                        default="transit",
                        help="Analysis mode for real targets")
    parser.add_argument("--window", type=int, default=None,
                        help="flatten() window length in cadences "
                             "(default: auto from the light curve's "
                             "cadence, ~2 days — mission-aware)")
    parser.add_argument("--quarters", type=int, default=None,
                        help="How many quarters/sectors to download and "
                             "stitch (default: all — Phase 5b)")
    parser.add_argument("--pinn", action="store_true",
                        help="Also train the Phase 4 PINN (transit mode)")
    parser.add_argument("--no-mask-transits", dest="mask_transits",
                        action="store_false",
                        help="Disable Phase 4b transit-masked flattening")
    parser.set_defaults(mask_transits=True)
    parser.add_argument("--vet", action="store_true",
                        help="Run Phase 10 vetting (odd/even, secondary, "
                             "SNR) and store a disposition")
    parser.add_argument("--centroid", action="store_true",
                        help="Also run the centroid-motion test (downloads "
                             "target pixel files; implies --vet)")
    parser.add_argument("--synthetic", action="store_true",
                        help="Process the offline demo targets instead")
    args = parser.parse_args()

    storage.init_db()

    targets = list(args.targets)
    if args.range:
        prefix, start, end = args.range
        targets += expand_range(prefix, int(start), int(end))

    if not targets and not args.synthetic:
        parser.error("Provide --targets ..., --range ..., or --synthetic")

    n_done = 0

    if args.synthetic:
        for name, params in DEMO_TARGETS.items():
            print(f"Processing {name} (synthetic, ground truth known)...")
            lc = make_synthetic_light_curve(params)
            if params.get("kind") in ("sine", "wr"):
                result, pinn_result = process_variability(
                    name, "Synthetic", lc,
                    teff=params["teff"],
                    stellar_radius=params["stellar_radius"],
                    use_pinn=args.pinn)
                print(f"  truth:     P={params['period_days']:.4f} d, "
                      f"amp={params['amplitude']:.4f}")
                print(f"  recovered: P={result['period_days']:.4f} d, "
                      f"amp={result['amplitude']:.4f}")
                if pinn_result:
                    print(f"  PINN:      P={pinn_result['period_days']:.4f} d, "
                          f"Q={pinn_result['quality_factor']:.1f} "
                          f"({'coherent' if pinn_result['quality_factor'] > 30 else 'stochastic'})")
            else:
                result, pinn_result = process_transit(
                    name, "Synthetic", lc, args.window,
                    teff=params["teff"],
                    stellar_radius=params["stellar_radius"],
                    use_pinn=args.pinn, mask_transits=args.mask_transits,
                    vet=args.vet or args.centroid, run_centroid=args.centroid)
                true_rp = np.sqrt(params["depth"])
                print(f"  truth:     depth={params['depth']:.5f}, "
                      f"Rp/R*={true_rp:.4f}")
                print(f"  BLS:       depth={result['depth']:.5f}, "
                      f"Rp/R*={result['rp_over_rstar']:.4f}")
                if pinn_result:
                    print(f"  PINN:      depth={pinn_result['depth']:.5f}, "
                          f"Rp/R*={pinn_result['rp_over_rstar']:.4f}")
            n_done += 1

    for target in targets:
        print(f"Processing {target} ({args.mission}, {args.mode})...")
        try:
            lc = fetch_light_curve(target, mission=args.mission,
                                   quarters=args.quarters)
            if lc is None:
                print(f"  no light curve found for {target}, skipping")
                continue
            teff, radius = get_stellar_params(lc)
            if args.mode == "variability":
                result, pinn_result = process_variability(
                    target, args.mission, lc, teff=teff,
                    stellar_radius=radius, use_pinn=args.pinn)
                line = (f"  P={result['period_days']:.4f} d, "
                        f"amp={result['amplitude']:.4f}, "
                        f"rms={result['rms']:.4f}")
                if pinn_result:
                    line += (f" | PINN Q={pinn_result['quality_factor']:.1f}")
                print(line)
            else:
                result, pinn_result = process_transit(
                    target, args.mission, lc, args.window,
                    teff=teff, stellar_radius=radius, use_pinn=args.pinn,
                    mask_transits=args.mask_transits,
                    vet=args.vet or args.centroid, run_centroid=args.centroid)
                line = (f"  BLS: P={result['period_days']:.4f} d, "
                        f"Rp/R*={result['rp_over_rstar']:.4f}")
                if pinn_result:
                    line += f" | PINN: Rp/R*={pinn_result['rp_over_rstar']:.4f}"
                print(line)
            n_done += 1
        except Exception as exc:
            # One bad target must not kill the batch.
            print(f"  FAILED on {target}: {exc}", file=sys.stderr)

    print(f"\nDone. {n_done} target(s) processed and stored.")
    print("Launch the dashboard with:  streamlit run app.py")


if __name__ == "__main__":
    main()
