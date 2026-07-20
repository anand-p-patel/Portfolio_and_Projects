"""
Preflight check. Run this first whenever something seems off:

    python check_setup.py

It verifies, in order: that the files in this folder belong to THIS project
(not another codebase sharing the directory), that all dependencies are
installed in THIS Python, that Playwright's browser is present, and what
state the database is in. [FAIL] lines block real runs; [WARN] lines are
one-command fixes.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
core_fail = False


def ok(msg): print("[OK]  ", msg)
def warn(msg): print("[WARN]", msg)
def fail(msg):
    global core_fail
    core_fail = True
    print("[FAIL]", msg)


print("USPSA Population Analytics — preflight")
print(f"folder: {HERE}")
print(f"python: {sys.version.split()[0]}  ({sys.executable})\n")

# 1 — do the files in this folder belong to THIS project?
MARKERS = {
    "config.py": 'PROJECT_TAG = "uspsa-analytics"',
    "dashboard.py": "USPSA Population Analytics",
    "scrape.py": "PractiScore",
    "report_parser.py": "$INFO",
    "db.py": "stage_scores",
    "analytics.py": "classifier",
}
for fname, marker in MARKERS.items():
    p = HERE / fname
    if not p.exists():
        fail(f"{fname} is missing — extract the FULL zip into one folder")
    elif marker not in p.read_text(encoding="utf-8", errors="replace"):
        fail(f"{fname} exists but belongs to a DIFFERENT project — this "
             "folder is shared with another codebase. Extract "
             "uspsa-analytics.zip into its own empty folder.")
    else:
        ok(f"{fname} belongs to this project")

# 2 — dependencies in THIS interpreter
for mod in ("sqlalchemy", "playwright", "pandas", "numpy", "streamlit", "plotly"):
    try:
        m = importlib.import_module(mod)
        ok(f"{mod} {getattr(m, '__version__', '')}".rstrip())
    except ImportError:
        fail(f"{mod} not installed in this Python — run: "
             "pip install -r requirements.txt")

# 3 — Playwright's browser (separate download from the library)
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = p.chromium.executable_path
        if exe and Path(exe).exists():
            ok("chromium browser installed")
        else:
            warn("chromium not installed — run: playwright install chromium")
except Exception as exc:
    warn(f"could not check the browser ({type(exc).__name__}) — "
         "run: playwright install chromium")

# 4 — database state
if not core_fail:
    try:
        sys.path.insert(0, str(HERE))
        import db
        eng = db.get_engine()
        db.init_db(eng)
        s = db.summary(eng)
        ok(f"database {eng.url} — {s['matches']} matches, "
           f"{s['stage_scores']:,} stage scores")
        if s["matches"] == 0:
            warn("database is empty — `python scrape.py --reparse-only` "
                 "loads the bundled real matches; `python seed_demo.py` "
                 "builds a synthetic season")
    except Exception as exc:
        fail(f"database layer failed: {exc}")
else:
    warn("skipping database check until the [FAIL] lines above are fixed")

# 5 — bundled sample data
raw = HERE / "data" / "raw_reports"
n = len(list(raw.glob("*.txt"))) if raw.exists() else 0
(ok if n else warn)(f"bundled real match reports: {n}")

print()
if core_fail:
    sys.exit("RESULT: NOT READY — fix the [FAIL] lines above, then re-run.")
print("RESULT: READY")
print("  scrape live data :  python scrape.py")
print("  open dashboard   :  streamlit run dashboard.py   "
      "(http://localhost:8531)")
