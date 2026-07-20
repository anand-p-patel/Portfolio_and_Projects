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
from pipeline.transform import flatten_light_curve
from pipeline.analyze import run_bls, run_variability
from pipeline.synthetic import make_synthetic_light_curve, DEMO_TARGETS
from db import storage


def expand_range(prefix: str, start: int, end: int):
    """'Kepler', 8, 12 -> ['Kepler-8', ..., 'Kepler-12']"""
    if end < start:
        start, end = end, start
    return [f"{prefix}-{i}" for i in range(start, end + 1)]


def process_transit(target_id, mission, lc, window,
                    teff=None, stellar_radius=None, use_pinn=False):
    """Transit path: flatten -> BLS -> (optional PINN) -> storage."""
    raw_time = np.asarray(lc.time.value, dtype=float)
    raw_flux = np.asarray(lc.flux.value, dtype=float)

    time, flux = flatten_light_curve(lc, window_length=window)
    result = run_bls(time, flux)

    storage.save_target(target_id, mission, raw_time, raw_flux, time, flux,
                        teff=teff, stellar_radius=stellar_radius)
    storage.save_result(target_id, result)

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
                        teff=None, stellar_radius=None):
    """Variability path: normalize (NO flatten) -> Lomb-Scargle."""
    raw_time = np.asarray(lc.time.value, dtype=float)
    raw_flux = np.asarray(lc.flux.value, dtype=float)

    norm = lc.normalize()
    time = np.asarray(norm.time.value, dtype=float)
    flux = np.asarray(norm.flux.value, dtype=float)

    result = run_variability(time, flux)
    storage.save_target(target_id, mission, raw_time, raw_flux, time, flux,
                        teff=teff, stellar_radius=stellar_radius)
    storage.save_result(target_id, result)
    return result


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
    parser.add_argument("--window", type=int, default=101,
                        help="flatten() window length in cadences")
    parser.add_argument("--pinn", action="store_true",
                        help="Also train the Phase 4 PINN (transit mode)")
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
            if params.get("kind") == "sine":
                result = process_variability(
                    name, "Synthetic", lc,
                    teff=params["teff"],
                    stellar_radius=params["stellar_radius"])
                print(f"  truth:     P={params['period_days']:.4f} d, "
                      f"amp={params['amplitude']:.4f}")
                print(f"  recovered: P={result['period_days']:.4f} d, "
                      f"amp={result['amplitude']:.4f}")
            else:
                result, pinn_result = process_transit(
                    name, "Synthetic", lc, args.window,
                    teff=params["teff"],
                    stellar_radius=params["stellar_radius"],
                    use_pinn=args.pinn)
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
            lc = fetch_light_curve(target, mission=args.mission)
            if lc is None:
                print(f"  no light curve found for {target}, skipping")
                continue
            teff, radius = get_stellar_params(lc)
            if args.mode == "variability":
                result = process_variability(target, args.mission, lc,
                                             teff=teff,
                                             stellar_radius=radius)
                print(f"  P={result['period_days']:.4f} d, "
                      f"amp={result['amplitude']:.4f}, "
                      f"rms={result['rms']:.4f}")
            else:
                result, pinn_result = process_transit(
                    target, args.mission, lc, args.window,
                    teff=teff, stellar_radius=radius, use_pinn=args.pinn)
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
