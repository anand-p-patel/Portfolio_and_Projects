"""
PHASE 1 — INGESTION. Human-in-the-loop PractiScore harvester.

Design (and why it looks this way):

  * practiscore.com sits behind Cloudflare and its robots.txt disallows
    automated crawling, and PractiScore staff have said there is no API.
    So this tool never tries to defeat anything: it opens a REAL, visible
    browser; YOU log the session past Cloudflare and drive the search page
    (pick your time frame, match type, region, hit Search, page through
    results). The script only *observes* the browser you are driving.

  * While you browse, two collectors run in the background:
      1. every anchor pointing at a /results/ page is harvested — that is
         the match list for your selected time frame;
      2. every JSON response the site makes is logged to
         data/discovery_log.jsonl (URL + top-level keys). This is the
         endpoint-discovery instrument: one browsing session tells you
         exactly which backend routes exist and what they return.

  * Per match, the primary data source is the JSON the PUBLIC results
    page already renders into itself (matchDef / scores / results JS
    vars) — divisions, classifications, DQ flags, classifier codes, and
    precomputed hit factors, all read straight out of the loaded page.
    NO LOGIN. The old login-gated plain-text "Web Report"
    (practiscore.com/reports/web/...) is kept only as a fallback for
    pages that don't embed the vars (e.g. old numeric-id matches).
    See embedded_parser.py for the JSON contract, report_parser.py for
    the text one; both yield the identical parsed structure.

Usage:
    # AUTOMATED (no human driving): search the match index by date, fetch all
    python scrape.py --start-date 2026-01-01 --end-date 2026-12-31
    python scrape.py --start-date 2026-06-01 --end-date 2026-06-30 --state TX
    python scrape.py --start-date .. --end-date .. --discover-only  # count only

    # INTERACTIVE (you drive the search page) / other
    python scrape.py                      # interactive search session
    python scrape.py --urls-file my.txt   # skip search; one results URL/line
    python scrape.py --reparse-only       # rebuild DB from saved raw files
    python scrape.py --limit 25 --delay 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

from sqlalchemy.orm import Session

# -- wrong-folder guard -----------------------------------------------------
# If Python resolves `config` to another project's config.py (two codebases
# sharing one folder), stop before importing anything else.
import config as _cfg
if getattr(_cfg, "PROJECT_TAG", None) != "uspsa-analytics":
    import sys as _sys
    _sys.exit(
        "\nSTOP: the config.py in this folder belongs to a different project,\n"
        "so this USPSA script would run against the wrong code.\n"
        "Extract uspsa-analytics.zip into its OWN folder and run from there.\n"
        "(`python check_setup.py` diagnoses folder problems.)")
# ---------------------------------------------------------------------------

import db
import embedded_parser
import match_search
import report_parser
from config import (DATA_DIR, DISCOVERY_LOG, MATCH_INDEX, PENDING_MATCHES,
                    RAW_HTML_DIR, RAW_REPORTS_DIR, SAMPLE_REPORTS_DIR,
                    SCRAPE_PROGRESS)

DEBUG_DIR = DATA_DIR / "debug"
# Persistent browser profile: your PractiScore login and the
# Cloudflare clearance survive between runs, so you sign in once.
PROFILE_DIR = DATA_DIR / "browser_profile"
ALLOW_NON_USPSA = False

# Override with env PS_SEARCH_URL for testing against a mock site.
SEARCH_URL = os.environ.get("PS_SEARCH_URL",
                            "https://practiscore.com/search/matches")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                     r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def source_key_for(url: str) -> str:
    """Stable key per match, derived from its results URL."""
    path = urlparse(url).path.strip("/")
    m = UUID_RE.search(path)
    if m:
        return m.group(0).lower()
    digits = re.findall(r"\d{4,}", path)
    if digits:
        return digits[-1]
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", path)[:100] or "unknown"


def log_discovery(entry: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DISCOVERY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


async def wait_for_enter(prompt: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, input, prompt)


# ---------------------------------------------------------------------------
# Phase A: interactive search session (you pick the time frame in the UI)
# ---------------------------------------------------------------------------
async def harvest_search_session(context, page) -> list[str]:
    seen: set[str] = set()

    async def on_response(response):
        """Endpoint discovery: log every JSON payload the site returns."""
        try:
            if "application/json" not in response.headers.get("content-type", ""):
                return
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": response.status,
                "url": response.url,
            }
            if response.status == 200:
                try:
                    data = await response.json()
                    if isinstance(data, dict):
                        entry["top_level_keys"] = sorted(data.keys())[:25]
                    elif isinstance(data, list):
                        entry["list_len"] = len(data)
                        if data and isinstance(data[0], dict):
                            entry["item_keys"] = sorted(data[0].keys())[:25]
                except Exception:
                    entry["note"] = "json parse failed"
            log_discovery(entry)
        except Exception:
            pass

    page.on("response", on_response)

    print("\n" + "=" * 70)
    print("A browser window is open on the PractiScore match search page.")
    print("1. Clear the Cloudflare check if it appears.")
    print("   NO LOGIN NEEDED — match data is read from the public results")
    print("   pages. (Signing in only helps the legacy Web Report fallback")
    print("   for the rare page that doesn't embed its data.)")
    print("2. Set MATCH TYPE = USPSA and pick YOUR DATE RANGE, then Search.")
    print("3. Page through every results page you want included.")
    print("   (Links are harvested automatically as each page renders.)")
    print("4. Come back here and press ENTER when you're done.")
    print("=" * 70)

    await page.goto(SEARCH_URL, timeout=180_000, wait_until="domcontentloaded")

    stop = asyncio.Event()

    async def harvest_once():
        try:
            hrefs = await page.eval_on_selector_all(
                "a[href*='/results/']", "els => els.map(e => e.href)")
            cand = {h.split("#")[0].split("?")[0].rstrip("/") for h in hrefs}
            # a real match link ends in an id/uuid; nav links like
            # /results or /results/search do not
            cand = {h for h in cand
                    if re.search(r"/results/[a-z]+/[0-9a-fA-F-]{4,}$", h)}
            new = cand - seen
            if new:
                seen.update(new)
                print(f"  [harvest] +{len(new)} match links "
                      f"({len(seen)} total)")
        except Exception:
            pass  # page mid-navigation; try again next tick

    async def collector():
        while not stop.is_set():
            await harvest_once()
            await asyncio.sleep(2)

    task = asyncio.create_task(collector())
    await wait_for_enter("\nPress ENTER here when finished browsing... ")
    stop.set()
    await task
    await harvest_once()  # final sweep of whatever is on screen now
    return sorted(seen)


# ---------------------------------------------------------------------------
# Phase B: per-match data capture.
#
# PRIMARY (no login): the public results page server-renders the whole match
# into inline JS variables (matchDef / scores / results). The browser has
# already parsed them, so we read them straight out of the page. See
# embedded_parser.py for the payload contract.
#
# FALLBACK (login-dependent): the legacy "Web Report" text file, for any
# page that doesn't embed the variables. Only works when signed in.
# ---------------------------------------------------------------------------
RESULTS_VIEWS = ("/results/all/", "/results/html/", "/results/new/",
                 "/results/")

# JS run inside the page: return the three data vars once they're populated
# (they start life as empty strings and fill in after the page's own script
# runs), else null so we keep polling.
_EMBEDDED_JS = """() => {
    try {
        if (typeof matchDef === 'object' && matchDef
                && matchDef.match_shooters
                && typeof results !== 'undefined' && results
                && results.length) {
            return {
                matchDef: matchDef,
                scores: (typeof scores === 'object' ? scores : null),
                results: results
            };
        }
    } catch (e) {}
    return null;
}"""


async def extract_page_data(page, results_url: str) -> tuple[dict | None, str]:
    """Load a public results page and pull its embedded match JSON.

    Returns (payload, reason). reason == "ok" -> payload saved.
    A reason starting with "skipping" means the match was deliberately
    excluded (e.g. non-USPSA) and must NOT trigger the Web Report
    fallback. Any other reason means embedded capture failed and the
    caller should try the fallback.
    """
    last_reason = "no embedded match data on results page"
    for view_url in results_url_variants(results_url):
        try:
            await page.goto(view_url, timeout=120_000,
                            wait_until="domcontentloaded")
        except Exception as exc:
            last_reason = f"page load failed: {exc}"
            continue

        payload = None
        for _ in range(20):  # up to ~10 s for the page script to populate
            try:
                payload = await page.evaluate(_EMBEDDED_JS)
            except Exception:
                payload = None
            if payload:
                break
            await page.wait_for_timeout(500)
        if not payload:
            continue  # this view didn't embed data; try the next variant

        region = embedded_parser._region(payload.get("matchDef") or {})
        if region and region.upper() != "USPSA" and not ALLOW_NON_USPSA:
            return None, (f"skipping {region} match "
                          "(use --allow-non-uspsa to keep it)")

        payload["meta"] = {
            "source_url": results_url,
            "view": view_url,
            "fetched_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
        }
        # Archive the rendered page too (regenerable insurance, gitignored).
        try:
            RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
            html = await page.content()
            (RAW_HTML_DIR / f"{source_key_for(results_url)}.html").write_text(
                html, encoding="utf-8")
        except Exception:
            pass  # archival is best-effort; the JSON is the parse source
        return payload, "ok"

    return None, last_reason


def results_url_variants(url: str) -> list[str]:
    """PractiScore serves the same match under several view paths, and the
    Web Report link is not present on all of them. Try each in turn."""
    out = [url]
    for view in RESULTS_VIEWS:
        if view in url:
            for alt in ("/results/new/", "/results/all/", "/results/html/"):
                cand = url.replace(view, alt)
                if cand not in out:
                    out.append(cand)
            break
    return out


def diagnose_blocked(text: str, final_url: str | None = None,
                     page_title: str = "") -> str:
    """Say WHY a fetch didn't return a web report, instead of guessing."""
    # Strip scripts first: analytics blobs contain digits like "500" that
    # trigger false positives on naive substring checks.
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text[:20000],
                  flags=re.S | re.I)
    low = body.lower()
    title = (page_title or "").strip().lower()
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", text[:20000], re.S | re.I)
        if m:
            title = " ".join(m.group(1).split()).lower()

    if "just a moment" in low or "cdn-cgi/challenge" in low:
        return "Cloudflare challenge — re-clear it in the browser window"
    homepage = (title.startswith("home |")
                or (final_url or "").rstrip("/").endswith("practiscore.com"))
    if homepage:
        return ("redirected to the PractiScore home page — the report needs a "
                "signed-in session; log in inside the browser window")
    if "$info" in low:
        region = "unknown"
        for line in text.splitlines()[:40]:
            if line.lower().startswith("$info region"):
                region = line.split(":", 1)[-1].strip()
                break
        return f"report is not a USPSA match (Region={region})"
    if ("log in" in low or "login" in low) and "register" in low:
        return "login required — sign in to PractiScore in the browser window"
    if "<html" in text[:2000].lower():
        return "server returned an HTML page, not a report"
    return "unrecognized content"


async def fetch_web_report(context, page, results_url: str) -> tuple[str | None, str]:
    """
    Try, in order: the browser context's HTTP client, an in-page fetch(),
    and finally navigating the tab straight to the report (exactly what a
    human clicking the link does). Whatever comes back that isn't a report
    is saved with a .json sidecar recording the URL requested, the HTTP
    status, and the URL we ended up at — so redirects are visible.
    """
    last_reason = "no Web Report link found on any results view"

    for view_url in results_url_variants(results_url):
        try:
            await page.goto(view_url, timeout=120_000, wait_until="domcontentloaded")
        except Exception as exc:
            last_reason = f"page load failed: {exc}"
            continue
        await page.wait_for_timeout(1500)

        href = await page.eval_on_selector_all(
            "a[href*='reports/web']", "els => els.length ? els[0].href : null")
        if not href:
            html = await page.content()
            m = re.search(r"https://practiscore\.com/reports/web[^\"'\s<>]*", html)
            href = m.group(0) if m else None
        if not href:
            continue  # try the next view

        report_url = urljoin(view_url, href)
        text, status, final_url, page_title = None, None, None, ""

        # 1. context request (shares cookies with the browser)
        try:
            resp = await context.request.get(report_url, timeout=60_000)
            status, final_url = resp.status, resp.url
            if resp.ok:
                text = await resp.text()
        except Exception:
            pass

        # 2. fetch() from inside the page
        if not (text and report_parser.looks_like_web_report(text)):
            try:
                text = await page.evaluate(
                    "url => fetch(url, {credentials: 'include'}).then(r => r.text())",
                    report_url)
            except Exception:
                pass

        # 3. Navigate the tab to it — identical to a human clicking the link.
        if not (text and report_parser.looks_like_web_report(text)):
            try:
                nav = await page.goto(report_url, timeout=60_000,
                                      wait_until="domcontentloaded")
                if nav is not None:
                    status = nav.status
                final_url = page.url
                page_title = await page.title()
                text = await page.evaluate(
                    "() => document.body ? document.body.innerText : ''")
            except Exception as exc:
                last_reason = f"web report fetch failed: {exc}"
                continue

        if text and report_parser.looks_like_web_report(text):
            region = report_parser.report_region(text)
            if region and region.upper() != "USPSA" and not ALLOW_NON_USPSA:
                return None, (f"skipping {region} match "
                              "(use --allow-non-uspsa to keep it)")
            return text, "ok"

        # Not a report. Save it, plus the metadata that explains why.
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        key = source_key_for(results_url)
        (DEBUG_DIR / f"{key}.html").write_text((text or "")[:20000],
                                               encoding="utf-8")
        (DEBUG_DIR / f"{key}.json").write_text(json.dumps({
            "results_url": results_url,
            "view_tried": view_url,
            "report_url": report_url,
            "http_status": status,
            "final_url": final_url,
            "page_title": page_title,
            "bytes": len(text or ""),
        }, indent=2), encoding="utf-8")
        last_reason = (f"{diagnose_blocked(text or '', final_url, page_title)} "
                       f"[saved {key}.html]")

    return None, last_reason


def _launch_kwargs(headless: bool) -> dict:
    launch_kw = dict(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        viewport={"width": 1360, "height": 900},
    )
    # Test hook: point at any Chromium binary (e.g. in CI sandboxes).
    if os.environ.get("PS_CHROMIUM_PATH"):
        launch_kw["executable_path"] = os.environ["PS_CHROMIUM_PATH"]
    return launch_kw


def write_progress(**fields) -> None:
    """Snapshot for the dashboard to poll. Best-effort; never fatal."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fields["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        SCRAPE_PROGRESS.write_text(json.dumps(fields), encoding="utf-8")
    except Exception:
        pass


async def fetch_one(context, page, url: str, refresh: bool) -> dict:
    """Capture one match's data (embedded JSON, else Web Report fallback).
    Returns an index record; does not sleep (caller paces politely)."""
    key = source_key_for(url)
    json_path = RAW_REPORTS_DIR / f"{key}.json"
    txt_path = RAW_REPORTS_DIR / f"{key}.txt"
    record = {"url": url, "source_key": key, "file": None, "status": None}

    cached = next((p for p in (json_path, txt_path) if p.exists()), None)
    if cached is not None and not refresh:
        record["file"] = str(cached)
        record["status"] = "cached"
        return record

    try:
        payload, reason = await extract_page_data(page, url)
        if payload:
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            record["file"] = str(json_path)
            record["status"] = "downloaded"
        elif reason.startswith("skipping"):
            record["status"] = f"skipped: {reason}"
        else:
            text, wreason = await fetch_web_report(context, page, url)
            if text:
                txt_path.write_text(text, encoding="utf-8")
                record["file"] = str(txt_path)
                record["status"] = "downloaded"
            else:
                record["status"] = f"skipped: {reason}; fallback: {wreason}"
    except Exception as exc:
        record["status"] = f"error: {exc}"
    return record


async def _fetch_urls(context, page, urls: list[str], delay: float,
                      refresh: bool, incremental_ingest: bool = False) -> list[dict]:
    """Phase B: fetch each match URL, pacing politely. Optionally ingest in
    batches so a long run's data appears in the dashboard as it grows."""
    index: list[dict] = []
    total = len(urls)
    saved = skipped = 0
    new_since_ingest: list[Path] = []
    print(f"\n[Phase B] Capturing match data for {total} matches "
          f"(~{delay:.0f}s apart — be nice to the site).\n")

    for i, url in enumerate(urls, 1):
        record = await fetch_one(context, page, url, refresh)
        key = record["source_key"]
        status = record["status"] or ""
        if status in ("downloaded",):
            saved += 1
            tag = "saved"
            if record["file"] and record["file"].endswith(".json"):
                tag = "saved   (embedded)"
            else:
                tag = "saved   (web report)"
            print(f"[{i}/{total}] {tag} {key}")
            if record["file"]:
                new_since_ingest.append(Path(record["file"]))
        elif status == "cached":
            print(f"[{i}/{total}] cached   {key}")
        elif status.startswith("skipped"):
            skipped += 1
            print(f"[{i}/{total}] skipped  {key} — {status[9:]}")
        else:
            print(f"[{i}/{total}] {status}  {key}")
        index.append(record)

        write_progress(state="fetching", total=total, done=i,
                       saved=saved, skipped=skipped, current=key)

        # Incremental ingest so partial data shows up mid-run (no prune).
        if incremental_ingest and len(new_since_ingest) >= 25:
            ingest_paths_quietly(new_since_ingest, index)
            new_since_ingest = []

        if i < total:  # no need to wait after the last one
            await asyncio.sleep(delay + random.uniform(0, delay / 2))

    if incremental_ingest and new_since_ingest:
        ingest_paths_quietly(new_since_ingest, index)

    MATCH_INDEX.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


async def download_all(urls: list[str], limit: int, delay: float,
                       refresh: bool, headless: bool = False) -> list[dict]:
    """Interactive path: harvest via the search session (or use given URLs),
    then fetch. Kept for manual/fallback use."""
    RAW_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        context = await p.chromium.launch_persistent_context(
            str(PROFILE_DIR), **_launch_kwargs(headless))
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            if not urls:
                urls = await harvest_search_session(context, page)
            if not urls:
                print("[Phase A] No match links collected. Nothing to do.")
                return []
            if limit:
                urls = urls[:limit]
            return await _fetch_urls(context, page, urls, delay, refresh)
        finally:
            await context.close()


async def run_automated(start: str, end: str, cap: int, state: str | None,
                        delay: float, refresh: bool, discover_only: bool,
                        headless_attempts: list[bool]) -> list[dict]:
    """Automated path: no human driving. Query the Algolia postmatches index
    for USPSA matches in [start, end] (optionally one state), then fetch each
    results page. Tries the browser modes in `headless_attempts` order (e.g.
    [True, False] = headless first, reopen visible if Cloudflare blocks the
    key-capture request)."""
    RAW_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    write_progress(state="discovering", message="opening browser")

    async with async_playwright() as p:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        context = page = app_id = api_key = None
        for idx, attempt_headless in enumerate(headless_attempts):
            last = idx == len(headless_attempts) - 1
            context = await p.chromium.launch_persistent_context(
                str(PROFILE_DIR), **_launch_kwargs(attempt_headless))
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                # Fail fast on a headless probe (Cloudflare usually blocks it);
                # give the visible/last attempt the full budget.
                app_id, api_key = await match_search.capture_search_key(
                    page, SEARCH_URL, timeout_ms=20_000 if last else 8_000)
                break
            except RuntimeError as exc:
                await context.close()
                context = None
                if not last:
                    print("[auto] headless blocked by Cloudflare — reopening "
                          "a visible window; clear the check if it appears.")
                    write_progress(state="discovering",
                                   message="Cloudflare — reopening visible")
                    continue
                write_progress(state="error", message=str(exc))
                raise

        try:
            loc = f" in {state.upper()}" if state else ""
            write_progress(state="discovering",
                           message=f"searching USPSA matches{loc}")
            print(f"[Phase A] Searching USPSA matches{loc} "
                  f"between {start} and {end} (via match index)…")
            matches = await match_search.discover_uspsa_matches(
                page, app_id, api_key, start, end, cap=cap, state=state)
            PENDING_MATCHES.write_text(json.dumps({
                "start": start, "end": end, "state": state,
                "count": len(matches), "matches": matches,
            }), encoding="utf-8")
            print(f"[Phase A] Found {len(matches)} USPSA matches.")

            if discover_only:
                write_progress(state="done", total=len(matches), done=0,
                               saved=0, skipped=0,
                               message=f"found {len(matches)} matches")
                return []

            if not matches:
                write_progress(state="done", total=0, done=0,
                               message="no matches in range")
                return []

            urls = [match_search.results_url(m["match_id"]) for m in matches]
            return await _fetch_urls(context, page, urls, delay, refresh,
                                     incremental_ingest=True)
        finally:
            if context is not None:
                await context.close()


# ---------------------------------------------------------------------------
# Phase C: parse raw reports -> SQL
# ---------------------------------------------------------------------------
def _parse_raw_file(path):
    """Route by extension: .json -> embedded_parser, .txt -> report_parser.
    Both return the same (parsed, stats) contract."""
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return embedded_parser.parse_embedded(payload)
    return report_parser.parse_report(
        path.read_text(encoding="utf-8", errors="replace"))


def _raw_files_by_key(source_dir) -> list:
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


def ingest_raw_reports(index: list[dict] | None = None, prune: bool = True) -> None:
    engine = db.get_engine()
    db.init_db(engine)

    # Ingest YOUR live corpus. Only if it's empty (e.g. a fresh clone with
    # no scraped data) do we fall back to the bundled sample matches, so a
    # reviewer still gets a working dashboard with zero setup.
    files = _raw_files_by_key(RAW_REPORTS_DIR)
    if not files:
        files = _raw_files_by_key(SAMPLE_REPORTS_DIR)
        if files:
            print(f"[Phase C] No live reports in {RAW_REPORTS_DIR}; "
                  f"using {len(files)} bundled sample match(es).")
    if not files:
        print("[Phase C] No reports found in", RAW_REPORTS_DIR,
              "or", SAMPLE_REPORTS_DIR)
        return
    url_by_key = {r["source_key"]: r["url"] for r in (index or [])}

    with Session(engine) as session:
        ok, failed = _ingest_paths(session, files, url_by_key)
        if prune:
            # Mirror disk: drop any match no longer backed by a report file
            # (e.g. the bundled samples once you've built a live corpus).
            removed = db.prune_matches(session, {p.stem for p in files})
            if removed:
                session.commit()
                print(f"  [db] pruned {removed} match(es) no longer on disk.")

    print(f"\n[Phase C] Ingested {ok} matches ({failed} failed).")
    print(db.summary(engine))
    print("\nNext:  streamlit run dashboard.py")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls-file", help="text file with one results URL per "
                                        "line (skips the search session)")
    ap.add_argument("--start-date", help="automated: earliest match date "
                                         "YYYY-MM-DD (enables the no-UI path)")
    ap.add_argument("--end-date", help="automated: latest match date YYYY-MM-DD")
    ap.add_argument("--state", help="automated: limit to a 2-letter state "
                                    "(e.g. TX); default all states")
    ap.add_argument("--cap", type=int, default=0,
                    help="automated: max matches to fetch (0 = no cap)")
    ap.add_argument("--discover-only", action="store_true",
                    help="automated: just search + write pending_matches.json, "
                         "don't download (powers the dashboard's confirm step)")
    ap.add_argument("--limit", type=int, default=0,
                    help="max matches to download this run (0 = all)")
    ap.add_argument("--delay", type=float, default=3.0,
                    help="base seconds between match pages (default 3)")
    ap.add_argument("--fresh-profile", action="store_true",
                    help="wipe the saved browser profile (log in again)")
    ap.add_argument("--allow-non-uspsa", action="store_true",
                    help="keep IPSC/SCSA/other-region matches "
                         "(default: USPSA only)")
    ap.add_argument("--headless", action="store_true",
                    help="run the browser headless (testing; Cloudflare "
                         "usually requires the visible window)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download reports that are already cached")
    ap.add_argument("--reparse-only", action="store_true",
                    help="no browser: rebuild the DB from data/raw_reports/")
    args = ap.parse_args()

    global ALLOW_NON_USPSA
    ALLOW_NON_USPSA = args.allow_non_uspsa

    if args.fresh_profile and PROFILE_DIR.exists():
        import shutil
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        print("Browser profile cleared — you'll need to log in again.")

    if args.reparse_only:
        ingest_raw_reports()
        return

    # -- Automated path: date range given, no human driving the search -----
    if args.start_date or args.end_date:
        if not (args.start_date and args.end_date):
            sys.exit("Automated mode needs both --start-date and --end-date.")
        try:
            datetime.strptime(args.start_date, "%Y-%m-%d")
            datetime.strptime(args.end_date, "%Y-%m-%d")
        except ValueError:
            sys.exit("Dates must be YYYY-MM-DD.")
        # Default: headless probe, then reopen visible if Cloudflare blocks.
        # --headless forces strict headless (testing/CI, no visible fallback).
        attempts = [True] if args.headless else [True, False]
        try:
            index = asyncio.run(run_automated(
                args.start_date, args.end_date, args.cap, args.state,
                args.delay, args.refresh, args.discover_only,
                headless_attempts=attempts))
        except RuntimeError as exc:
            sys.exit(f"\nAutomated run failed: {exc}")
        if not args.discover_only:
            write_progress(state="ingesting", message="loading database")
            ingest_raw_reports(index, prune=True)
            write_progress(state="done", total=len(index),
                           done=len(index),
                           saved=sum(1 for r in index
                                     if r["status"] == "downloaded"),
                           skipped=sum(1 for r in index
                                       if (r["status"] or "").startswith("skip")),
                           message="complete")
        return

    urls: list[str] = []
    if args.urls_file:
        urls = [ln.strip() for ln in open(args.urls_file, encoding="utf-8")
                if ln.strip() and not ln.startswith("#")]
        print(f"Loaded {len(urls)} result URLs from {args.urls_file}")

    index = asyncio.run(download_all(urls, args.limit, args.delay,
                                 args.refresh, args.headless))
    ingest_raw_reports(index)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")



