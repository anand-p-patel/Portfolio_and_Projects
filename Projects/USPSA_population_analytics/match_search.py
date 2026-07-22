"""
Automated match discovery via PractiScore's Algolia search index.

PractiScore's match search is Algolia-backed. The `postmatches` index
catalogs completed matches (the ones with posted results) and — crucially —
lives on `algolia.net`, which is NOT behind Cloudflare. So we can list
"every USPSA match in a date range" with a few JSON queries instead of the
human driving the search UI. Each record carries:
    match_id          the UUID -> results URL (/results/new/{id})
    match_date        "YYYY-MM-DD"
    match_subtype     the sport; "uspsa" is the USPSA filter (a facet)
    front_club_state  2-letter state (a facet; the `state` field is empty)
    timestamp_utc_updated  numeric, filterable (proxy for results-post time)

Two facts shape the query strategy (both verified live 2026-07-19):
  * `match_date` is a plain string, NOT range-filterable in Algolia. We
    bound each query with numericFilters on `timestamp_utc_updated` (with a
    buffer for post-lag) and then filter each hit's match_date exactly,
    client-side.
  * Algolia only pages through ~1000 hits per query (paginationLimitedTo).
    A wide range (e.g. a year, thousands of USPSA matches) exceeds that, so
    we split the range into MONTHLY sub-windows and paginate within each.

The search key is a short-lived scoped key the site hands its own frontend;
`capture_search_key` reads it from the site's own Algolia request during a
single search-page visit (which also warms Cloudflare for the per-match
fetches). Only the pure helpers below are unit-tested; the browser calls are
covered by the live smoke test.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

# The app id is stable (embedded in the site's Algolia host); the api key is
# fetched fresh per run. Kept here as the documented default / fallback.
ALGOLIA_APP_ID = "1X6B6XDR0H"
POSTMATCHES_INDEX = "postmatches"
RESULTS_URL_TEMPLATE = "https://practiscore.com/results/new/{match_id}"

# timestamp_utc_updated is when results were posted, which lags the match
# date. Widen the numeric bound so no in-range match is missed; the exact
# match_date filter trims the extra.
_UPDATED_LEAD_DAYS = 30      # results posted up to ~a month after the match
_UPDATED_TRAIL_DAYS = 7      # ...and occasionally edited a few days later
_HITS_PER_PAGE = 1000        # Algolia max


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def _to_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def monthly_windows(start, end) -> list[tuple[date, date]]:
    """Split [start, end] into (first-of-month … last-of-month) sub-windows,
    each clamped to the requested bounds. Keeps every Algolia query under the
    ~1000-hit pagination ceiling."""
    start, end = _to_date(start), _to_date(end)
    if end < start:
        return []
    out = []
    cur = start.replace(day=1)
    while cur <= end:
        # first day of the next month
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        win_start = max(start, cur)
        win_end = min(end, nxt - timedelta(days=1))
        out.append((win_start, win_end))
        cur = nxt
    return out


def updated_bounds(win_start, win_end) -> tuple[int, int]:
    """Epoch-second bounds for the `timestamp_utc_updated` numericFilter,
    padded for the match-date-vs-post-date lag."""
    lo = datetime.combine(_to_date(win_start), datetime.min.time(),
                          tzinfo=timezone.utc) - timedelta(days=_UPDATED_LEAD_DAYS)
    hi = datetime.combine(_to_date(win_end), datetime.max.time(),
                          tzinfo=timezone.utc) + timedelta(days=_UPDATED_TRAIL_DAYS)
    return int(lo.timestamp()), int(hi.timestamp())


def in_range(match_date, start, end) -> bool:
    """Is match_date (a 'YYYY-MM-DD' string) within [start, end] inclusive?"""
    if not match_date:
        return False
    try:
        md = _to_date(match_date)
    except (ValueError, TypeError):
        return False
    return _to_date(start) <= md <= _to_date(end)


def results_url(match_id: str) -> str:
    """Build the public results-page URL for a match UUID."""
    return RESULTS_URL_TEMPLATE.format(match_id=match_id)


def build_query_params(win_start, win_end, page: int, state=None) -> str:
    """Algolia `params` query string for one postmatches page: USPSA (+state)
    facet filters, numeric bound on updated-time, one page of hits."""
    lo, hi = updated_bounds(win_start, win_end)
    facets = ["match_subtype:uspsa"]
    if state:
        facets.append(f"front_club_state:{state.upper()}")
    numeric = [f"timestamp_utc_updated>={lo}", f"timestamp_utc_updated<={hi}"]
    parts = {
        "query": "",
        "hitsPerPage": str(_HITS_PER_PAGE),
        "page": str(page),
        "facetFilters": json.dumps(facets),
        "numericFilters": json.dumps(numeric),
    }
    from urllib.parse import urlencode
    return urlencode(parts)


def hits_to_matches(hits: list[dict], start, end) -> list[dict]:
    """Map raw Algolia hits to our match dicts, keeping only in-range ones
    that have a usable match_id."""
    out = []
    for h in hits:
        mid = h.get("match_id")
        md = h.get("match_date")
        if not mid or not in_range(md, start, end):
            continue
        out.append({
            "match_id": mid,
            "match_date": md,
            "name": h.get("match_name") or "",
            "state": h.get("front_club_state") or None,
        })
    return out


def dedupe_and_sort(matches: list[dict], cap: int = 0) -> list[dict]:
    """Dedupe on match_id, sort by match_date desc, optionally truncate."""
    by_id = {}
    for m in matches:
        by_id.setdefault(m["match_id"], m)
    ordered = sorted(by_id.values(),
                     key=lambda m: (m.get("match_date") or ""), reverse=True)
    return ordered[:cap] if cap and cap > 0 else ordered


def key_from_request_url(url: str) -> tuple[str | None, str | None]:
    """Pull (app_id, api_key) out of a captured Algolia request URL."""
    qs = parse_qs(urlparse(url or "").query)
    return (qs.get("x-algolia-application-id", [None])[0],
            qs.get("x-algolia-api-key", [None])[0])


# ---------------------------------------------------------------------------
# Browser-backed calls (covered by the live smoke test, not unit tests)
# ---------------------------------------------------------------------------
async def capture_search_key(page, search_url: str,
                             timeout_ms: int = 20_000) -> tuple[str, str]:
    """Visit the search page and read the scoped Algolia key from the site's
    own request. Also warms Cloudflare for the per-match fetches. Raises
    RuntimeError if no key appears (usually a Cloudflare challenge in
    headless mode — the caller should retry visible)."""
    captured = {"url": None}

    def on_request(req):
        if "algolia.net" in req.url and "queries" in req.url and not captured["url"]:
            captured["url"] = req.url

    page.on("request", on_request)
    try:
        await page.goto(search_url, wait_until="domcontentloaded",
                        timeout=120_000)
        waited = 0
        while waited < timeout_ms and not captured["url"]:
            await page.wait_for_timeout(500)
            waited += 500
    finally:
        page.remove_listener("request", on_request)

    app_id, api_key = key_from_request_url(captured["url"] or "")
    if not api_key:
        raise RuntimeError(
            "no Algolia key captured — likely a Cloudflare challenge; "
            "retry with a visible browser window")
    return app_id or ALGOLIA_APP_ID, api_key


async def _query_page(page, app_id, api_key, params: str) -> dict:
    """One postmatches query via in-page fetch (same-origin CORS to Algolia,
    exactly as the site's JS does it)."""
    return await page.evaluate(
        """async ([appId, apiKey, index, params]) => {
            const url = `https://${appId}-dsn.algolia.net/1/indexes/${index}/query`;
            const r = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-Algolia-Application-Id': appId,
                    'X-Algolia-API-Key': apiKey,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({params})
            });
            const j = await r.json();
            return {status: r.status, nbHits: j.nbHits, hits: j.hits || [],
                    nbPages: j.nbPages, message: j.message || null};
        }""",
        [app_id, api_key, POSTMATCHES_INDEX, params])


async def discover_uspsa_matches(page, app_id, api_key, start, end,
                                 cap: int = 0, state=None,
                                 on_progress=None) -> list[dict]:
    """List USPSA matches (optionally in one state) with results in
    [start, end]. Chunks the range monthly and paginates within each window
    to stay under Algolia's ~1000-hit ceiling. Returns match dicts sorted
    newest-first, deduped."""
    collected: list[dict] = []
    windows = monthly_windows(start, end)
    for wi, (ws, we) in enumerate(windows, 1):
        page_no = 0
        while True:
            params = build_query_params(ws, we, page_no, state)
            res = await _query_page(page, app_id, api_key, params)
            if res.get("message"):
                raise RuntimeError(f"Algolia error: {res['message']}")
            hits = res.get("hits", [])
            collected.extend(hits_to_matches(hits, start, end))
            n_pages = res.get("nbPages") or 1
            page_no += 1
            if page_no >= n_pages or page_no * _HITS_PER_PAGE >= 1000:
                break
        if on_progress:
            on_progress(wi, len(windows), len(dedupe_and_sort(collected)))
    return dedupe_and_sort(collected, cap)


if __name__ == "__main__":
    # Quick manual check of the pure helpers.
    ws = monthly_windows("2025-01-15", "2025-03-10")
    print("monthly windows for 2025-01-15..2025-03-10:")
    for a, b in ws:
        print(" ", a, "->", b)
    print("results_url:", results_url("06e7f238-53f2-4265-a22a-4aa7c8a21c17"))
    print("in_range 2025-02-01 in Jan..Mar:",
          in_range("2025-02-01", "2025-01-15", "2025-03-10"))
