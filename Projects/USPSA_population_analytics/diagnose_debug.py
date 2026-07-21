"""
Read the pages saved in data/debug/ and say what the server actually sent.

When a report fetch comes back as something other than a web report, the
response is saved instead of discarded. This script summarizes those files
so the cause is identifiable rather than guessed at.

    python diagnose_debug.py            # summary of every saved page
    python diagnose_debug.py --full 1   # dump the first file in full
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEBUG_DIR = Path(__file__).resolve().parent / "data" / "debug"

# Signature -> what it means. Order matters; first hit wins.
SIGNATURES = [
    ("cloudflare challenge", ("just a moment", "cf-challenge", "cdn-cgi/challenge",
                              "checking your browser", "turnstile")),
    ("login / auth wall", ("please log in", "sign in to continue", 'type="password"',
                           "login-form", "auth/login")),
    ("404 / not found", ("404", "not found", "page you requested")),
    ("403 / forbidden", ("403", "forbidden", "access denied")),
    ("500 / server error", ("500", "internal server error", "whoops")),
    ("rate limited", ("429", "too many requests", "slow down")),
    ("maintenance", ("maintenance", "temporarily unavailable")),
    ("homepage bounce — needs a signed-in session",
     ("home | practiscore", "toggle navigation")),
    ("results page (not the report)", ("mainresultsdiv", "match breakdown",
                                       "practiscore")),
]


def strip_code(text: str) -> str:
    """Remove script/style blocks — analytics blobs contain digits like
    500/429 that trigger false positives on substring matching."""
    return re.sub(r"<script.*?</script>|<style.*?</style>", " ", text,
                  flags=re.S | re.I)


def classify(text: str) -> list[str]:
    low = strip_code(text).lower()
    hits = [name for name, needles in SIGNATURES
            if any(n in low for n in needles)]
    return hits or ["unrecognized"]


def summarize(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    low = text.lower()

    title = "—"
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    if m:
        title = " ".join(m.group(1).split())[:90]

    print(f"\n=== {path.name}")
    side = path.with_suffix(".json")
    if side.exists():
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
            print(f"  requested : {meta.get('report_url')}")
            print(f"  status    : {meta.get('http_status')}")
            if meta.get("final_url") != meta.get("report_url"):
                print(f"  ENDED AT  : {meta.get('final_url')}  <-- redirected")
            if meta.get("page_title"):
                print(f"  page title: {meta['page_title']}")
        except Exception:
            pass
    print(f"  size      : {len(text):,} chars")
    print(f"  <title>   : {title}")
    print(f"  looks like: {', '.join(classify(text))}")

    # Is it actually a report that just failed the sniff test?
    if "$info" in low:
        region = next((l.split(":", 1)[-1].strip()
                       for l in text.splitlines()[:60]
                       if l.lower().startswith("$info region")), "?")
        print(f"  !! contains $INFO — this IS a report (Region={region})")

    # Redirects tell us where the site wanted to send us.
    for pat, label in ((r'http-equiv=["\']refresh["\'][^>]*url=([^"\'>]+)', "meta refresh"),
                       (r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)', "js redirect")):
        r = re.search(pat, text, re.I)
        if r:
            print(f"  {label}: {r.group(1)[:100]}")

    # Any report links present on the page we landed on?
    links = re.findall(r'href=["\']([^"\']*reports?/[^"\']*)["\']', text, re.I)
    if links:
        print(f"  report-ish links: {sorted(set(links))[:4]}")

    body = " ".join(re.sub(r"<[^>]+>", " ", strip_code(text)).split())
    print(f"  visible text: {body[:220] or '(none)'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", type=int, default=0,
                    help="also dump the first N files verbatim")
    args = ap.parse_args()

    if not DEBUG_DIR.exists():
        raise SystemExit(f"No debug folder at {DEBUG_DIR} — nothing was saved. "
                         "Run scrape.py first.")
    files = sorted(DEBUG_DIR.glob("*.html"))
    if not files:
        raise SystemExit(f"{DEBUG_DIR} is empty — nothing to diagnose.")

    print(f"Diagnosing {len(files)} saved response(s) in {DEBUG_DIR}")
    for f in files:
        summarize(f)

    print("\n" + "=" * 60)
    tally: dict[str, int] = {}
    for f in files:
        for k in classify(f.read_text(encoding="utf-8", errors="replace")):
            tally[k] = tally.get(k, 0) + 1
    print("VERDICT:", ", ".join(f"{k} × {v}" for k, v in
                                sorted(tally.items(), key=lambda x: -x[1])))

    for f in files[:args.full]:
        print(f"\n{'=' * 60}\nFULL CONTENT — {f.name}\n{'=' * 60}")
        print(f.read_text(encoding="utf-8", errors="replace")[:6000])


if __name__ == "__main__":
    main()
