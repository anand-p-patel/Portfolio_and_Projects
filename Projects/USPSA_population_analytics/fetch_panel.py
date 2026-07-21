"""
Dashboard "⚡ Fetch live data" panel: trigger automated scraping by date
range, with no search-page driving.

The scrape is a long, browser-driven job that fights Streamlit's rerun loop
if run in-process, so this launches `scrape.py` as a detached subprocess and
communicates through two small JSON files it polls:
  * pending_matches.json — written by `--discover-only`; the confirm count
  * scrape_progress.json — written continuously during the fetch

Flow (state kept in st.session_state under the "fetch_" prefix):
  idle → [Find matches] → discovering → confirm(N, ETA) → [Fetch]
       → fetching(progress bar) → done → [Reload data]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import streamlit as st

from config import PENDING_MATCHES, PROJECT_ROOT, SCRAPE_PROGRESS, RAW_REPORTS_DIR


def scraping_available() -> bool:
    """True only where a Playwright browser is installed — i.e. a local
    machine after `playwright install chromium`. Hosted platforms like
    Streamlit Community Cloud have no browser (and PractiScore's anti-bot
    layer blocks datacenter IPs anyway), so the live-fetch UI is hidden
    there and the app runs on its bundled corpus instead. Pure filesystem
    check — no Playwright import, safe inside Streamlit's event loop."""
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    roots = [Path(env)] if env else []
    home = Path.home()
    roots += [
        home / "AppData" / "Local" / "ms-playwright",   # Windows
        home / ".cache" / "ms-playwright",              # Linux
        home / "Library" / "Caches" / "ms-playwright",  # macOS
    ]
    return any(r.exists() and any(r.glob("chromium-*")) for r in roots)

# US state codes for the optional filter (dropdown). "All" = no state filter.
_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY",
]
_DELAY = 3.0  # keep in step with scrape.py's default; used for ETA only


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _clear_signal_files():
    for p in (PENDING_MATCHES, SCRAPE_PROGRESS):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _launch(extra_args: list[str]) -> subprocess.Popen:
    """Launch scrape.py in the background with this venv's python."""
    cmd = [sys.executable, "scrape.py", *extra_args]
    return subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))


def _uncached_count(matches: list[dict]) -> int:
    """How many of these matches aren't already on disk (so a resumed run's
    ETA is honest)."""
    n = 0
    for m in matches:
        mid = m.get("match_id", "")
        if not (RAW_REPORTS_DIR / f"{mid}.json").exists() \
                and not (RAW_REPORTS_DIR / f"{mid}.txt").exists():
            n += 1
    return n


def _fmt_eta(n_matches: int) -> str:
    secs = int(n_matches * _DELAY * 1.25)  # +25% for jitter/parse
    if secs < 90:
        return f"~{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"~{mins} min"
    return f"~{mins // 60}h {mins % 60}m"


def _ss(key, default=None):
    return st.session_state.setdefault(f"fetch_{key}", default)


def render_fetch_panel(default_lo: date, default_hi: date) -> None:
    """Render the fetch controls + live status. Safe to call with an empty
    database (that's exactly when you'd want to fetch)."""
    st.subheader("⚡ Fetch live data")

    if not scraping_available():
        # Hosted deploy (no local browser). Show the demo notice, not controls.
        st.info(
            "**Live scraping runs on a local machine only.** This hosted demo "
            "runs on a bundled corpus of real USPSA matches. PractiScore is "
            "behind Cloudflare and blocks cloud-datacenter IPs, so the "
            "browser-driven scraper can't run here.\n\n"
            "Clone the repo and run it locally to pull any date range yourself "
            "— see the README.",
            icon=":material/cloud_off:")
        return

    phase = _ss("phase", "idle")

    # -- Inputs (always visible) -------------------------------------------
    picked = st.date_input("Fetch matches dated", (default_lo, default_hi),
                           key="fetch_range")
    state = st.selectbox("State (optional)", ["All"] + _STATES, index=0,
                         key="fetch_state",
                         help="Limit to one state to keep a run small; "
                              "'All' fetches every USPSA match in the range.")
    disabled = phase in ("discovering", "fetching")

    if st.button("Find matches", disabled=disabled, key="fetch_find"):
        if not (isinstance(picked, tuple) and len(picked) == 2):
            st.warning("Pick both ends of the fetch date range.")
        else:
            _clear_signal_files()
            lo, hi = picked
            args = ["--start-date", lo.isoformat(),
                    "--end-date", hi.isoformat(), "--discover-only"]
            if state != "All":
                args += ["--state", state]
            _ss("proc")  # ensure key exists
            st.session_state["fetch_proc"] = _launch(args)
            st.session_state["fetch_phase"] = "discovering"
            st.session_state["fetch_args"] = {"lo": lo.isoformat(),
                                              "hi": hi.isoformat(),
                                              "state": state}
            st.rerun()

    # -- Discovering -------------------------------------------------------
    if phase == "discovering":
        prog = _read_json(SCRAPE_PROGRESS) or {}
        pend = _read_json(PENDING_MATCHES)
        if pend is not None and prog.get("state") in ("done", None) \
                and prog.get("state") != "error":
            st.session_state["fetch_pending"] = pend
            st.session_state["fetch_phase"] = "confirm"
            st.rerun()
        elif prog.get("state") == "error":
            st.error(f"Discovery failed: {prog.get('message')}")
            st.session_state["fetch_phase"] = "idle"
        else:
            st.info(f"Searching… {prog.get('message', 'starting')}")
            time.sleep(1.5)
            st.rerun()

    # -- Confirm -----------------------------------------------------------
    if phase == "confirm":
        pend = _ss("pending") or {}
        matches = pend.get("matches", [])
        total = len(matches)
        new = _uncached_count(matches)
        cached = total - new
        if total == 0:
            st.warning("No USPSA matches found in that range.")
            if st.button("OK", key="fetch_ok0"):
                st.session_state["fetch_phase"] = "idle"
                st.rerun()
        else:
            cached_note = f" ({cached} already downloaded)" if cached else ""
            st.success(f"Found **{total}** USPSA matches — {new} new to "
                       f"fetch{cached_note}. Est. {_fmt_eta(new)}.")
            c1, c2 = st.columns(2)
            if c1.button(f"Fetch {new}", key="fetch_go", disabled=new == 0):
                _clear_signal_files()
                a = _ss("args")
                args = ["--start-date", a["lo"], "--end-date", a["hi"]]
                if a["state"] != "All":
                    args += ["--state", a["state"]]
                st.session_state["fetch_proc"] = _launch(args)
                st.session_state["fetch_phase"] = "fetching"
                st.rerun()
            if c2.button("Cancel", key="fetch_cancel"):
                st.session_state["fetch_phase"] = "idle"
                st.rerun()

    # -- Fetching ----------------------------------------------------------
    if phase == "fetching":
        prog = _read_json(SCRAPE_PROGRESS) or {}
        state_ = prog.get("state")
        if state_ == "error":
            st.error(f"Scrape failed: {prog.get('message')}")
            st.session_state["fetch_phase"] = "idle"
        elif state_ == "done":
            st.success(f"Done — {prog.get('saved', 0)} saved, "
                       f"{prog.get('skipped', 0)} skipped.")
            if st.button("Reload data", key="fetch_reload"):
                st.session_state["fetch_phase"] = "idle"
                st.cache_data.clear()
                st.rerun()
        else:
            total = prog.get("total") or 0
            done = prog.get("done") or 0
            if state_ == "ingesting":
                st.info("Loading database…")
            elif total:
                st.progress(min(done / total, 1.0),
                            text=f"{done}/{total} · {prog.get('saved', 0)} saved "
                                 f"· {prog.get('current', '')[:8]}")
            else:
                st.info(f"Working… {prog.get('message', '')}")
            time.sleep(2)
            st.rerun()
