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

  * Per match, the primary data source is the plain-text "Web Report"
    (practiscore.com/reports/web/...) linked from every USPSA results
    page. It contains divisions, classifications, DQ flags, classifier
    codes per stage, and precomputed hit factors — everything Phases 2-3
    need, in one authenticated GET made with the browser's own cookies.

Usage:
    python scrape.py                      # interactive search session
    python scrape.py --urls-file my.txt   # skip search; one results URL/line
    python scrape.py --reparse-only       # rebuild DB from saved raw files
    python scrape.py --limit 25 --delay 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

from sqlalchemy.orm import Session

import db
import report_parser
from config import DATA_DIR, DISCOVERY_LOG, MATCH_INDEX, RAW_REPORTS_DIR

SEARCH_URL = "https://practiscore.com/search/matches"
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
    print("2. Set MATCH TYPE = USPSA and pick YOUR DATE RANGE, then Search.")
    print("3. Page through every results page you want included.")
    print("   (Links are harvested automatically as each page renders.)")
    print("4. Come back here and press ENTER when you're done.")
    print("=" * 70)

    await page.goto(SEARCH_URL, timeout=180_000, wait_until="domcontentloaded")

    stop = asyncio.Event()

    async def collector():
        while not stop.is_set():
            try:
                hrefs = await page.eval_on_selector_all(
                    "a[href*='/results/']", "els => els.map(e => e.href)")
                new = {h.split("#")[0] for h in hrefs} - seen
                if new:
                    seen.update(new)
                    print(f"  [harvest] +{len(new)} match links "
                          f"({len(seen)} total)")
            except Exception:
                pass  # page mid-navigation; try again next tick
            await asyncio.sleep(2)

    task = asyncio.create_task(collector())
    await wait_for_enter("\nPress ENTER here when finished browsing... ")
    stop.set()
    await task
    return sorted(seen)


# ---------------------------------------------------------------------------
# Phase B: per-match web-report download (browser's own cookies)
# ---------------------------------------------------------------------------
async def fetch_web_report(context, page, results_url: str) -> tuple[str | None, str]:
    """Returns (report_text | None, reason)."""
    await page.goto(results_url, timeout=120_000, wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)

    href = await page.eval_on_selector_all(
        "a[href*='reports/web']", "els => els.length ? els[0].href : null")
    if not href:
        # Some layouts render the link late or behind a menu; scan raw HTML.
        html = await page.content()
        m = re.search(r"https://practiscore\.com/reports/web[^\"'\s<>]*", html)
        href = m.group(0) if m else None
    if not href:
        return None, "no Web Report link on results page (non-USPSA match?)"

    report_url = urljoin(results_url, href)

    # 1st try: context.request shares the context's cookies (incl. Cloudflare).
    try:
        resp = await context.request.get(report_url, timeout=60_000)
        if resp.ok:
            text = await resp.text()
            if report_parser.looks_like_web_report(text):
                return text, "ok"
    except Exception as exc:
        print(f"    context.request failed ({exc}); trying in-page fetch...")

    # 2nd try: fetch() inside the page itself (guaranteed same session).
    try:
        text = await page.evaluate(
            "url => fetch(url, {credentials: 'include'}).then(r => r.text())",
            report_url)
        if report_parser.looks_like_web_report(text):
            return text, "ok"
        return None, "web report URL returned non-report content (blocked?)"
    except Exception as exc:
        return None, f"web report fetch failed: {exc}"


async def download_all(urls: list[str], limit: int, delay: float,
                       refresh: bool) -> list[dict]:
    RAW_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    index: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1360, "height": 900})
        page = await context.new_page()

        # ---- Phase A (only if we weren't handed URLs) --------------------
        if not urls:
            urls = await harvest_search_session(context, page)
        if not urls:
            print("[Phase A] No match links collected. Nothing to do.")
            await browser.close()
            return index
        if limit:
            urls = urls[:limit]
        print(f"\n[Phase B] Downloading web reports for {len(urls)} matches "
              f"(~{delay:.0f}s apart — be nice to the site).\n")

        # ---- Phase B ------------------------------------------------------
        for i, url in enumerate(urls, 1):
            key = source_key_for(url)
            out_path = RAW_REPORTS_DIR / f"{key}.txt"
            record = {"url": url, "source_key": key,
                      "file": str(out_path), "status": None}

            if out_path.exists() and not refresh:
                record["status"] = "cached"
                print(f"[{i}/{len(urls)}] cached   {key}")
            else:
                try:
                    text, reason = await fetch_web_report(context, page, url)
                    if text:
                        out_path.write_text(text, encoding="utf-8")
                        record["status"] = "downloaded"
                        print(f"[{i}/{len(urls)}] saved    {key}")
                    else:
                        record["status"] = f"skipped: {reason}"
                        print(f"[{i}/{len(urls)}] skipped  {key} — {reason}")
                except Exception as exc:
                    record["status"] = f"error: {exc}"
                    print(f"[{i}/{len(urls)}] ERROR    {key} — {exc}")
                await asyncio.sleep(delay + random.uniform(0, delay / 2))

            index.append(record)

        await browser.close()

    MATCH_INDEX.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


# ---------------------------------------------------------------------------
# Phase C: parse raw reports -> SQL
# ---------------------------------------------------------------------------
def ingest_raw_reports(index: list[dict] | None = None) -> None:
    engine = db.get_engine()
    db.init_db(engine)

    files = sorted(RAW_REPORTS_DIR.glob("*.txt"))
    if not files:
        print("[Phase C] No raw reports found in", RAW_REPORTS_DIR)
        return
    url_by_key = {r["source_key"]: r["url"] for r in (index or [])}

    ok = failed = 0
    with Session(engine) as session:
        for path in files:
            key = path.stem
            try:
                parsed, stats = report_parser.parse_report(
                    path.read_text(encoding="utf-8", errors="replace"))
                db.upsert_match(session, parsed, source_key=key,
                                source_url=url_by_key.get(key))
                session.commit()
                ok += 1
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
                print(f"  [db] FAILED {path.name}: {exc}")

    print(f"\n[Phase C] Ingested {ok} matches ({failed} failed).")
    print(db.summary(engine))
    print("\nNext:  streamlit run dashboard.py")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls-file", help="text file with one results URL per "
                                        "line (skips the search session)")
    ap.add_argument("--limit", type=int, default=0,
                    help="max matches to download this run (0 = all)")
    ap.add_argument("--delay", type=float, default=3.0,
                    help="base seconds between match pages (default 3)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-download reports that are already cached")
    ap.add_argument("--reparse-only", action="store_true",
                    help="no browser: rebuild the DB from data/raw_reports/")
    args = ap.parse_args()

    if args.reparse_only:
        ingest_raw_reports()
        return

    urls: list[str] = []
    if args.urls_file:
        urls = [ln.strip() for ln in open(args.urls_file, encoding="utf-8")
                if ln.strip() and not ln.startswith("#")]
        print(f"Loaded {len(urls)} result URLs from {args.urls_file}")

    index = asyncio.run(download_all(urls, args.limit, args.delay, args.refresh))
    ingest_raw_reports(index)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
