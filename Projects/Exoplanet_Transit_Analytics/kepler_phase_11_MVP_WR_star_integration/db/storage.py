"""
SQL persistence layer (SQLite).

Design notes
------------
- Arrays live on disk as compressed .npz files; the database stores
  metadata + file path + derived results. Keeping bulk arrays out of
  the DB is the standard pattern (same idea as a star schema keeping
  facts small and pointing at large payloads).
- results has a `method` column ("bls" now, "pinn" in Phase 4) with a
  composite primary key, so the PINN slots in with ZERO schema changes
  and the dashboard can compare methods side by side.
- SQLite is zero-config for local dev; swapping to Postgres for
  deployment changes the connection line, not the schema.
"""

import io
import json
import os
import sqlite3
from datetime import datetime, timezone

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Paths are environment-overridable so a deployment (e.g. Streamlit
# Community Cloud) can point at a bundled read-only DB and data dir
# without code changes. Defaults are the in-repo locations.
DB_PATH = os.environ.get("KEPLER_DB", os.path.join(_ROOT, "kepler.db"))
DATA_DIR = os.environ.get("KEPLER_DATA_DIR",
                          os.path.join(_ROOT, "data", "processed"))


def _resolve_npz(stored_path: str) -> str:
    """
    Resolve a target's .npz path portably. The DB stores the absolute
    path from the machine that processed the target; on another machine
    (a cloud deploy from a cloned repo) that path won't exist, so fall
    back to the same filename under the current DATA_DIR.
    """
    if os.path.exists(stored_path):
        return stored_path
    return os.path.join(DATA_DIR, os.path.basename(stored_path))


def _connect(db_path: str = DB_PATH):
    return sqlite3.connect(db_path)


def init_db(db_path: str = DB_PATH):
    """Create tables if they don't exist. Safe to call every run."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS targets (
                target_id    TEXT PRIMARY KEY,
                mission      TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                n_points     INTEGER NOT NULL,
                data_path    TEXT NOT NULL,
                teff         REAL,
                stellar_radius REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                target_id     TEXT NOT NULL,
                method        TEXT NOT NULL,
                period_days   REAL,
                t0            REAL,
                duration_days REAL,
                depth         REAL,
                rp_over_rstar REAL,
                PRIMARY KEY (target_id, method),
                FOREIGN KEY (target_id) REFERENCES targets(target_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vetting (
                target_id     TEXT PRIMARY KEY,
                disposition   TEXT,
                snr           REAL,
                depth         REAL,
                rp_over_rstar REAL,
                n_transits    INTEGER,
                odd_depth     REAL,
                even_depth    REAL,
                oddeven_sigma REAL,
                secondary_depth REAL,
                secondary_snr REAL,
                centroid_shift_pixels REAL,
                centroid_sigma REAL,
                centroid_note TEXT,
                flags         TEXT,
                vetted_at     TEXT,
                FOREIGN KEY (target_id) REFERENCES targets(target_id)
            )
            """
        )
        # Lightweight migrations: add columns to DBs created before
        # they existed. SQLite raises OperationalError if the column
        # is already present — safe to ignore.
        for table, col in (("targets", "teff"),
                           ("targets", "stellar_radius"),
                           ("results", "amplitude"),
                           ("results", "rms"),
                           ("results", "quality_factor")):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} REAL")
            except sqlite3.OperationalError:
                pass


def save_target(target_id, mission, raw_time, raw_flux, time, flux,
                teff=None, stellar_radius=None, db_path: str = DB_PATH):
    """Save raw + flattened arrays to .npz and register the target
    with its host-star parameters (Teff in K, radius in R_sun)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    safe_name = target_id.replace(" ", "_").replace("/", "_")
    data_path = os.path.join(DATA_DIR, f"{safe_name}.npz")

    np.savez_compressed(
        data_path,
        raw_time=raw_time, raw_flux=raw_flux,
        time=time, flux=flux,
    )

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO targets (target_id, mission, processed_at,
                                 n_points, data_path, teff, stellar_radius)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_id) DO UPDATE SET
                mission=excluded.mission,
                processed_at=excluded.processed_at,
                n_points=excluded.n_points,
                data_path=excluded.data_path,
                teff=excluded.teff,
                stellar_radius=excluded.stellar_radius
            """,
            (target_id, mission,
             datetime.now(timezone.utc).isoformat(timespec="seconds"),
             len(time), data_path, teff, stellar_radius),
        )


def save_result(target_id, result: dict, db_path: str = DB_PATH):
    """Upsert one analysis result (bls, pinn, or variability)."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO results (target_id, method, period_days, t0,
                                 duration_days, depth, rp_over_rstar,
                                 amplitude, rms, quality_factor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_id, method) DO UPDATE SET
                period_days=excluded.period_days,
                t0=excluded.t0,
                duration_days=excluded.duration_days,
                depth=excluded.depth,
                rp_over_rstar=excluded.rp_over_rstar,
                amplitude=excluded.amplitude,
                rms=excluded.rms,
                quality_factor=excluded.quality_factor
            """,
            (target_id, result["method"], result.get("period_days"),
             result.get("t0"), result.get("duration_days"),
             result.get("depth"), result.get("rp_over_rstar"),
             result.get("amplitude"), result.get("rms"),
             result.get("quality_factor")),
        )


def save_vetting(target_id, vet: dict, db_path: str = DB_PATH):
    """Upsert a target's vetting report (Phase 10)."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO vetting (target_id, disposition, snr, depth,
                rp_over_rstar, n_transits, odd_depth, even_depth,
                oddeven_sigma, secondary_depth, secondary_snr,
                centroid_shift_pixels, centroid_sigma, centroid_note,
                flags, vetted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_id) DO UPDATE SET
                disposition=excluded.disposition, snr=excluded.snr,
                depth=excluded.depth, rp_over_rstar=excluded.rp_over_rstar,
                n_transits=excluded.n_transits, odd_depth=excluded.odd_depth,
                even_depth=excluded.even_depth,
                oddeven_sigma=excluded.oddeven_sigma,
                secondary_depth=excluded.secondary_depth,
                secondary_snr=excluded.secondary_snr,
                centroid_shift_pixels=excluded.centroid_shift_pixels,
                centroid_sigma=excluded.centroid_sigma,
                centroid_note=excluded.centroid_note,
                flags=excluded.flags, vetted_at=excluded.vetted_at
            """,
            (target_id, vet.get("disposition"), vet.get("snr"),
             vet.get("depth"), vet.get("rp_over_rstar"),
             vet.get("n_transits"), vet.get("odd_depth"),
             vet.get("even_depth"), vet.get("oddeven_sigma"),
             vet.get("secondary_depth"), vet.get("secondary_snr"),
             vet.get("centroid_shift_pixels"), vet.get("centroid_sigma"),
             vet.get("centroid_note"),
             json.dumps(vet.get("flags", [])),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def load_vetting(target_id, db_path: str = DB_PATH):
    """Return a target's stored vetting report as a dict, or None."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT disposition, snr, depth, rp_over_rstar, n_transits, "
            "odd_depth, even_depth, oddeven_sigma, secondary_depth, "
            "secondary_snr, centroid_shift_pixels, centroid_sigma, "
            "centroid_note, flags FROM vetting WHERE target_id = ?",
            (target_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "disposition": row[0], "snr": row[1], "depth": row[2],
        "rp_over_rstar": row[3], "n_transits": row[4],
        "odd_depth": row[5], "even_depth": row[6], "oddeven_sigma": row[7],
        "secondary_depth": row[8], "secondary_snr": row[9],
        "centroid_shift_pixels": row[10], "centroid_sigma": row[11],
        "centroid_note": row[12],
        "flags": json.loads(row[13]) if row[13] else [],
    }


def save_pinn_profile(target_id, phase_days, flux_model,
                      prefix: str = "pinn", db_path: str = DB_PATH):
    """
    Append a PINN's fitted model curve to the target's .npz so the
    dashboard can overlay it WITHOUT importing torch (train offline,
    serve plain arrays). `prefix` is "pinn" for the transit PINN and
    "pinn_var" for the variability PINN, keeping the two curves separate.
    """
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT data_path FROM targets WHERE target_id = ?",
            (target_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"{target_id} not found in targets table")
    path = _resolve_npz(row[0])
    arrays = dict(np.load(path))
    arrays[f"{prefix}_phase"] = np.asarray(phase_days, dtype=float)
    arrays[f"{prefix}_flux"] = np.asarray(flux_model, dtype=float)
    np.savez_compressed(path, **arrays)


def list_targets(db_path: str = DB_PATH):
    """Return [(target_id, mission, processed_at, n_points), ...]"""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT target_id, mission, processed_at, n_points "
            "FROM targets ORDER BY target_id"
        ).fetchall()
    return rows


def list_missions(db_path: str = DB_PATH):
    """Distinct missions present in the DB, e.g. ['Kepler', 'Synthetic']."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT mission FROM targets ORDER BY mission"
        ).fetchall()
    return [r[0] for r in rows]


def list_targets_for_mission(mission, db_path: str = DB_PATH):
    """Processed target_ids for one mission, ordered naturally-ish."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT target_id FROM targets WHERE mission = ? "
            "ORDER BY target_id", (mission,)
        ).fetchall()
    return [r[0] for r in rows]


def get_random_target(db_path: str = DB_PATH):
    """One random processed target_id, or None if the DB is empty."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT target_id FROM targets ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    return row[0] if row else None


def load_target(target_id, db_path: str = DB_PATH):
    """
    Load everything the dashboard needs for one target.

    Returns dict: {target_id, mission, arrays..., results: {method: dict}}
    or None if the target isn't in the DB.
    """
    with _connect(db_path) as conn:
        trow = conn.execute(
            "SELECT target_id, mission, processed_at, n_points, data_path, "
            "teff, stellar_radius "
            "FROM targets WHERE target_id = ?", (target_id,)
        ).fetchone()
        if trow is None:
            return None
        rrows = conn.execute(
            "SELECT method, period_days, t0, duration_days, depth, "
            "rp_over_rstar, amplitude, rms, quality_factor "
            "FROM results WHERE target_id = ?", (target_id,)
        ).fetchall()

    arrays = np.load(_resolve_npz(trow[4]))
    results = {
        r[0]: {
            "method": r[0], "period_days": r[1], "t0": r[2],
            "duration_days": r[3], "depth": r[4], "rp_over_rstar": r[5],
            "amplitude": r[6], "rms": r[7], "quality_factor": r[8],
        }
        for r in rrows
    }
    out = {
        "target_id": trow[0],
        "mission": trow[1],
        "processed_at": trow[2],
        "n_points": trow[3],
        "teff": trow[5],
        "stellar_radius": trow[6],
        "raw_time": arrays["raw_time"], "raw_flux": arrays["raw_flux"],
        "time": arrays["time"], "flux": arrays["flux"],
        "results": results,
    }
    for key in ("pinn_phase", "pinn_flux", "pinn_var_phase", "pinn_var_flux"):
        out[key] = arrays[key] if key in arrays.files else None
    out["vetting"] = load_vetting(target_id, db_path)
    return out
