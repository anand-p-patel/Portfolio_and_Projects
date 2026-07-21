# Automated date-range scraping from the dashboard — design

Date: 2026-07-19. Status: approved (approach A).

## Why

Today match discovery is human-in-the-loop: the user opens a Chromium
window, sets Match Type + date range in PractiScore's search UI, and pages
through results while `scrape.py` observes. The goal: set the date range in
the Streamlit dashboard, click a button, and have the matches fetched
automatically — no manual search-page driving, no clicking each match.

## Feasibility (spiked live 2026-07-19)

PractiScore's match search is Algolia-backed. The **`postmatches`** index
(342k records) catalogs completed matches with results. Each record has:
- `match_id` — the UUID that builds the results URL
  (`https://practiscore.com/results/new/{match_id}`)
- `match_date` — "YYYY-MM-DD"
- `match_subtype` — the sport; **`uspsa`** has 56,141 records (the USPSA
  filter). `match_type` is NOT a facet; `match_subtype` IS.
- `timestamp_utc_updated` — numeric, filterable (proxy for post time)

The Algolia endpoint (`{appId}-dsn.algolia.net`, appId `1X6B6XDR0H`) is
**not** behind Cloudflare and accepts the public scoped search key the
site's own frontend uses. The key is short-lived; we capture a fresh one
from the site's own Algolia request during a single search-page visit.

Constraints found:
- `match_date` is a plain string — not range-filterable in Algolia
  directly. Bound the query with `numericFilters` on
  `timestamp_utc_updated` (buffer: window_start − 30d … window_end + 7d for
  post-lag), then filter each hit's `match_date` client-side to the exact
  window.
- **Algolia pagination is limited to ~1,000 hits per query**
  (`paginationLimitedTo`). A wide range (e.g. a full year, potentially
  thousands of USPSA matches) exceeds this. So discovery **chunks the
  requested range into sub-windows** (month by month) and paginates within
  each, so no single query needs more than ~1,000 hits. Results are merged
  and deduped on `match_id`.
- The per-match **results pages are still Cloudflare-fronted and
  JS-rendered**, so fetching them still needs a real browser session with
  Cloudflare clearance (the persistent profile). Only discovery is
  Cloudflare-free.

## Decisions (user-approved)

1. **Run mode:** background process + live progress in the dashboard; user
   keeps using the UI and clicks "Reload data" when done.
2. **Browser:** headless by default; auto-relaunch visible if a Cloudflare
   challenge is detected, so the user clears it once, then continue.
3. **Volume:** no hard cap (a year of data needs thousands of matches).
   Instead, the dashboard's confirm step shows the match count **and an
   estimated duration** (≈ count × delay) so a large run is a deliberate
   choice. Runs are resumable: already-fetched matches are cached and
   skipped, so an interrupted multi-hour run continues where it left off
   on the next click. An optional `--cap` remains for quick test runs
   (default 0 = no cap).

## Architecture (approach A — subprocess + progress files)

Streamlit's event loop and Playwright's asyncio browser conflict
in-process, so the dashboard drives the scraper as a **detached
subprocess** and communicates through small JSON files it polls. The
existing Phase B/C pipeline is reused unchanged.

### New module `match_search.py` (pure, testable)
- `capture_search_key(page) -> (app_id, api_key)` — visit the search page
  once (warms Cloudflare), read the site's own Algolia request to grab the
  scoped key.
- `discover_uspsa_matches(page, start_date, end_date, cap=0, state=None)`
  → split [start, end] into monthly sub-windows; for each, query
  `postmatches` via in-page fetch (`facetFilters=match_subtype:uspsa`, plus
  `front_club_state:{state}` when a state is given; `numericFilters`
  bounding `timestamp_utc_updated`), paginating (hitsPerPage 1000) until
  exhausted or the ~1000 limit; keep hits whose `match_date` ∈ [start,
  end]. Merge sub-windows, dedupe on `match_id`, **sort by `match_date`
  desc** (don't rely on index ranking). `cap>0` truncates (test runs
  only); `cap=0` returns all. Returns `[{match_id, match_date, name,
  state}]`. State is the 2-letter `front_club_state` facet (verified: TX,
  CA, FL… populated; the `state` field is empty in this index).
- Pure helpers split out for unit tests: range→monthly sub-windows,
  window→numeric-bounds, hit→results URL, in-range predicate, merge/dedupe.

### `scrape.py` changes (new non-interactive path)
- `--start-date YYYY-MM-DD --end-date YYYY-MM-DD [--cap N] [--state XX]` →
  run `match_search` discovery in place of interactive Phase A, build
  results URLs, then existing Phase B (embedded extraction) + C
  (ingest/prune).
- `--discover-only` → discovery only; write `data/pending_matches.json`
  (`{start, end, count, matches:[...]}`); no fetching. Powers the
  dashboard's count/confirm.
- No dates → the existing interactive session still runs (kept as
  fallback for edge cases / manual use).
- Browser: launch headless; on Cloudflare challenge (during key capture or
  first fetch) relaunch visible, reusing the persistent profile.
- Progress: write `data/scrape_progress.json`
  (`{state: discovering|fetching|done|error, total, done, saved, skipped,
  current, message, ts}`) after each match so the dashboard can render it.
- **Incremental ingest:** because year-scale runs last hours, run Phase C
  ingest periodically (every ~25 saved matches) as well as at the end, so
  the dashboard shows the corpus growing on each "Reload data" mid-run
  rather than only when finished. (Prune runs only on the final ingest, so
  partial progress is never mistaken for a shrunken corpus.)

### `dashboard.py` changes (sidebar "⚡ Fetch live data")
- Date range inputs (default to the current view range), an optional
  state dropdown (All / 2-letter states), and a "Find matches" button.
- "Find matches" → launch `scrape.py --discover-only …` (background); when
  `pending_matches.json` lands, show "Found N USPSA matches — est. ~Xh Ym
  at {delay}s each (M already cached, so ~K new to fetch)." The estimate
  counts only uncached matches so a resumed run reads honestly.
- Confirm ("Fetch") → launch `scrape.py --start-date … --end-date …`
  (background). Poll `scrape_progress.json`, render a progress bar; on
  `done`, show summary + "Reload data" (calls `load_frames.clear()`).
  Interrupting and re-clicking resumes (cached matches skip).
- Subprocess launched with the repo's venv python, detached
  (non-blocking); a lightweight auto-refresh polls the progress file.

## Data flow

Dashboard button → `scrape.py --discover-only` → Algolia (Cloudflare-free)
→ `pending_matches.json` → dashboard shows count → confirm →
`scrape.py --start-date …` → per match: results page (Cloudflare, browser)
→ embedded JSON → `raw_reports/*.json` → Phase C ingest + prune →
`scrape_progress.json` state=done → dashboard "Reload data".

## Error handling
- Expired/again key or Cloudflare block → progress file `state=error` with
  a plain message; headless run auto-retries visible once.
- Per-match failures keep the existing debug-sidecar behavior and the
  skipped/saved counts; one bad match never aborts the run.
- **Resumability is the guard for long runs**, not a cap: a multi-hour
  fetch that dies (Cloudflare, sleep, closed laptop) leaves cached matches
  on disk, so re-clicking "Fetch" continues from where it stopped. The
  confirm step's count + ETA is the guard against *unintentionally* large
  runs.
- All existing politeness stays (≥3s jittered delay, USPSA filter, no
  Cloudflare bypass attempts). Discovery adds only a handful of
  Cloudflare-free Algolia queries per month of range.
- Stale progress/pending files are cleared at the start of each run.

## Testing
- `match_search` pure helpers against recorded Algolia-response fixtures:
  window→bounds math, hit→URL, in-range date filtering, cap.
- Live smoke: a narrow (~1 week) USPSA range end-to-end → saved matches,
  clean ingest, 0 HF sanity flags.
- Dashboard: discover → count → confirm → progress → reload, on a small
  range.
- Unchanged: reviewer path (`--reparse-only`), sample fallback, port 8531.

## Invariant change
CLAUDE.md invariant 3 shifts from human-*driven* to human-*triggered*: the
user triggers a bounded, capped run with a date range rather than operating
the search by hand. Discovery uses the site's own public search API at low
volume; per-match fetches keep the jittered delay, USPSA-only default, and
no-Cloudflare-bypass stance. Update the wording; keep the safeguards.
