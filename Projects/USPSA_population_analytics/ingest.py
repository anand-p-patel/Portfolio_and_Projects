"""
Phase C — parse raw reports into SQL. No browser, no network: this is the
seam between the scraped files on disk and the database, so both the scraper
(`scrape.py`) and the dashboard (for its zero-config bootstrap) can call it
without pulling in Playwright.

Two parse sources, one contract:
  * data/raw_reports/*.json -> embedded_parser  (login-free primary)
  * data/raw_reports/*.txt  -> report_parser    (Web Report fallback)
Both yield {match, stages, competitors, scores}, so db.upsert_match doesn't
care which produced it.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

import db
import embedded_parser
import report_parser
from config import RAW_REPORTS_DIR, SAMPLE_REPORTS_DIR


def _parse_raw_file(path: Path):
    """Route by extension: .json -> embedded_parser, .txt -> report_parser.
    Both return the same (parsed, stats) contract."""
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return embedded_parser.parse_embedded(payload)
    return report_parser.parse_report(
        path.read_text(encoding="utf-8", errors="replace"))


def raw_files_by_key(source_dir: Path) -> list[Path]:
    """One parse source per match in `source_dir`. If a match has both a
    .json (embedded) and a .txt (web report), the .json wins — it's the
    login-free source and carries the same fields."""
    by_key: dict[str, Path] = {}
    for path in sorted(source_dir.glob("*.txt")):
        by_key[path.stem] = path
    for path in sorted(source_dir.glob("*.json")):
        if path.stem in by_key:
            print(f"  [db] note: {path.stem} has both .json and .txt; "
                  "using .json (embedded)")
        by_key[path.stem] = path  # json overrides txt
    return [by_key[k] for k in sorted(by_key)]


def _ingest_paths(session, paths, url_by_key, verbose=True) -> tuple[int, int]:
    """Upsert each report file into the DB. Returns (ok, failed)."""
    ok = failed = 0
    for path in paths:
        key = path.stem
        try:
            parsed, stats = _parse_raw_file(path)
            db.upsert_match(session, parsed, source_key=key,
                            source_url=url_by_key.get(key))
            session.commit()
            ok += 1
            if verbose:
                flags = ""
                if stats.hf_sanity_violations:
                    flags = f"  ⚠ {stats.hf_sanity_violations} HF sanity flags"
                print(f"  [db] {parsed['match']['match_date']}  "
                      f"{parsed['match']['name'][:48]:<48} "
                      f"{stats.competitors:>3} shooters, "
                      f"{stats.scores:>4} scores{flags}")
        except Exception as exc:
            session.rollback()
            failed += 1
            if verbose:
                print(f"  [db] FAILED {path.name}: {exc}")
    return ok, failed


def ingest_paths_quietly(paths, index: list[dict]) -> None:
    """Incremental mid-run ingest of just-downloaded files (no prune, quiet).
    Lets a long run's data appear in the dashboard as it accumulates."""
    engine = db.get_engine()
    db.init_db(engine)
    url_by_key = {r["source_key"]: r["url"] for r in index}
    with Session(engine) as session:
        _ingest_paths(session, paths, url_by_key, verbose=False)


def ingest_raw_reports(index: list[dict] | None = None, prune: bool = True,
                       verbose: bool = True) -> int:
    """Load the live corpus (data/raw_reports/) into SQL, falling back to the
    bundled samples when it's empty. Returns the number of matches ingested."""
    engine = db.get_engine()
    db.init_db(engine)

    # Ingest YOUR live corpus. Only if it's empty (e.g. a fresh clone or a
    # hosted deploy with no scraped data) do we fall back to the bundled
    # sample matches, so the dashboard is never blank with zero setup.
    files = raw_files_by_key(RAW_REPORTS_DIR)
    if not files:
        files = raw_files_by_key(SAMPLE_REPORTS_DIR)
        if files and verbose:
            print(f"[Phase C] No live reports in {RAW_REPORTS_DIR}; "
                  f"using {len(files)} bundled sample match(es).")
    if not files:
        if verbose:
            print("[Phase C] No reports found in", RAW_REPORTS_DIR,
                  "or", SAMPLE_REPORTS_DIR)
        return 0
    url_by_key = {r["source_key"]: r["url"] for r in (index or [])}

    with Session(engine) as session:
        ok, failed = _ingest_paths(session, files, url_by_key, verbose=verbose)
        if prune:
            # Mirror disk: drop any match no longer backed by a report file
            # (e.g. the bundled samples once you've built a live corpus).
            removed = db.prune_matches(session, {p.stem for p in files})
            if removed:
                session.commit()
                if verbose:
                    print(f"  [db] pruned {removed} match(es) no longer on disk.")

    if verbose:
        print(f"\n[Phase C] Ingested {ok} matches ({failed} failed).")
        print(db.summary(engine))
        print("\nNext:  streamlit run dashboard.py")
    return ok
