# CLAUDE.md — USPSA Population Analytics Engine

Context for Claude Code. Read fully before changing anything. Everything in
"Hard-won facts" was established empirically — against 49 real PractiScore
reports and live-site runs — and must not be re-derived, second-guessed, or
"fixed" back to the intuitive-but-wrong version.

## What this is

A portfolio data-engineering project (owner: Anand, pivoting physics → data):
scrape USPSA match results from practiscore.com, load a SQL star schema, and
serve two analyses in a Streamlit dashboard — division participation trends
over a user-selected time frame, and classification (GM…U) vs classifier-stage
difficulty via Z-score normalization.

Pipeline: `scrape.py` (Playwright) → `data/raw_reports/` → parse → `db.py`
(SQLAlchemy; SQLite default, `DATABASE_URL` for Postgres) → `analytics.py`
(pandas + Z-scores) → `dashboard.py` (Streamlit/Plotly; local port 8531 via
`--server.port`, default 8501 elsewhere).
Match discovery is automated: `match_search.py` queries PractiScore's
Algolia `postmatches` index for USPSA matches in a date range (no UI
driving); the dashboard's "⚡ Fetch live data" panel (`fetch_panel.py`)
triggers it as a background subprocess. See the "Automated discovery"
facts below and `docs/superpowers/specs/2026-07-19-automated-date-range-
scraping-design.md`. Two parse sources / two parsers, one output contract:
- `*.json` (embedded JSON from a public results page) → `embedded_parser.py`
  — **the primary, login-free path** (see below).
- `*.txt` (PractiScore "Web Report") → `report_parser.py` — the legacy
  fallback for pages that don't embed JSON (needs a signed-in session).
Your live scraped corpus lands in `data/raw_reports/` (gitignored). The
tracked demo corpus in `data/sample_reports/` is a real month of Texas
USPSA matches (June 2026: 32 matches, 1,344 entries, 7,482 stage scores)
and is ingested only as a fallback when `raw_reports/` is empty — this is
what the hosted demo shows. Three Web Report `.txt` files kept as the
text-parser reference live in `data/reference/web_report_samples/`.
Ingestion mirrors disk: `--reparse-only` prunes DB matches whose report
file is gone (see `db.prune_matches`).
Both return the identical `{match, stages, competitors, scores}` dict, so
`db.upsert_match` / `analytics` / `dashboard` never know which was used.
Phase C (parse raw files → SQL) lives in `ingest.py` (no Playwright), so
`dashboard.py` reuses it to self-bootstrap from `sample_reports` when the DB
is empty (fresh clone / hosted deploy). `fetch_panel.py` hides the live-fetch
UI when no local browser is present (`scraping_available()`), so a Streamlit
Cloud deploy shows the bundled-corpus demo + a notice instead — the scraper
is local-only (Cloudflare blocks datacenter IPs).
Support tools: `check_setup.py` (preflight), `diagnose_debug.py` (reads
`data/debug/` failure artifacts), `seed_demo.py` (synthetic season).

## Current status (2026-07-19)

WORKING, verified on this machine: the credential-free path. On a fresh
clone (empty `data/raw_reports/`), `python scrape.py --reparse-only`
falls back to the `data/sample_reports/` demo (32 real TX matches, 1,344
entries, 7,482 stage scores, 0 HF sanity flags) and `streamlit run
dashboard.py` renders everything at http://localhost:8531. Once you've
scraped live matches, the same command mirrors your live corpus instead
(the demo is dropped).

WORKING (2026-07-19): fully automated date-range scraping. Set a date
range (+ optional state) in the dashboard's "⚡ Fetch live data" panel →
it discovers USPSA matches via Algolia and fetches them in the
background, no search-page driving. Verified end-to-end: TX 1-week
discovery found 14 matches; a capped fetch saved + ingested cleanly.
The old interactive search session still works with no date args.

RESOLVED (was: "live downloads need login"). The login-gated Web Report
is no longer the primary source. Public results pages server-render the
whole match into inline JS (`matchDef`/`scores`/`results`); Phase B reads
those straight out of the rendered page — **no login needed**. Verified
2026-07-19 on a live match: 10 shooters, 8 stages, 80 scores, 0 HF sanity
violations. The Web Report path is kept only as a fallback (see pipeline).
Design: `docs/superpowers/specs/2026-07-19-embedded-json-ingestion-design.md`.

VERIFIED end-to-end on a live USPSA match (2026-07-19, embedded path):
`06e7f238-53f2-4265-a22a-4aa7c8a21c17` "Gun Craft Practical Shooters",
65 shooters, 7 stages, 448 scores, 0 skipped, **0 HF sanity violations**.
Member numbers present 61/65 (real USPSA formats e.g. A183965, TY125984);
classes span B–M+U; divisions PCC/CO/LO/Open/Limited/Production; both
power factors; one real classifier stage (code 20-02) with procedurals
reconciled correctly. The IPSC-sample gaps (all-U, no members, no
classifier) were data-specific, not code issues — nothing left open here.

## Hard-won facts — do not re-derive

**Web Report text format** (validated against 49 real reports, 10,497
competitors, 126,629 score rows; details in `report_parser.py` comments and
README "How this was verified"):
- `E` lines (37 fields): 0 comp#, 1 member#, 2 first, 3 last, 4 DQ,
  8 classification, 9 division, 10 match points, 11 place, 12 power factor.
- `G` lines (9 fields): 0 stage#, 2 min rounds, 3 max points,
  4 classifier yes/no, 5 classifier code, 6 name, 7 scoring. >9 fields means
  a comma inside the stage name; the parser folds extras back into the name.
- `I` lines (32 fields): 1 stage#, 2 comp#, 3 per-stage DQ, 5–10 A B C D M NS,
  11 procedurals, 19 penalty points, 25 time, 27 total points (net),
  28 hit factor, 29 stage points, 30 stage place.
- **`I` field 4 is NOT DNF.** It is a near-constant per-match app flag, "Yes"
  on ~60% of valid scores. Treating it as DNF silently discards most data.
  DNF is *derived*: no time AND no points AND no HF.
- HF == total_points / time to 4 decimals in 100.0% of timed rows. The parser
  flags violations (`hf_sanity_violations`); a nonzero count after ingest
  means a column shift and must be investigated, never suppressed.

**Embedded JSON in public results pages** (validated 2026-07-19; details in
`embedded_parser.py` comments and the design doc):
- Modern (UUID) results pages define three JS vars: `matchDef` (name, date,
  club, `match_subtype` for region, `match_shooters`, `match_stages`,
  `match_pfs`), `scores` (raw per-stage strings/hits — not needed),
  `results` (PractiScore's precomputed standings: `results[0]` match-level,
  `results[i>=1]` per-stage rows with A/C/D/M/NS, Time, HF, stage pts, place).
- Scoring point values come from `match_pfs` (the match's own major/minor
  table), never hardcoded. `results.details` has no procedurals: net points
  (`round(HF×Time)`) and procedurals are *reconciled* from hit counts, and
  that reconciliation IS the HF sanity check (must stay 0 across the corpus).
- **`results.details.APEN` = arbitrary penalty points** (an RO deduction, NOT
  a ×10 procedural). The reconciliation subtracts it:
  `HF×Time == gross − APEN − 10·procedurals`. Verified against real TX
  matches — without subtracting APEN, ~0.1% of rows false-flag the HF check.
  Do not remove the APEN term.
- **Old numeric-ID matches do NOT embed these vars** — `/results/new/{id}`
  bounces to search; `/results/html/{id}` is a static table. The extraction
  guard (`matchDef` must be an object with `match_shooters`) rejects the
  empty stub and falls through to the Web Report fallback. Do not "fix" this.
- IPSC/Steel matches run in the USPSA app carry `match_type` `uspsa_p` but
  `match_subtype` `ipsc`/`sc`; region is derived from the subtype and the
  USPSA-only default skips them (same as the text path's `$INFO Region`).
- **Two-in-one matches reuse stage display numbers** (e.g. 1,2,3,4,1,2,3,4
  with distinct `stage_uuid`s). `embedded_parser` numbers stages by their
  1-based POSITION in `match_stages` (aligned with how score rows index
  stages via the `results` array), NOT by `stage_number` — the display
  number collides on the DB `(match_id, number)` key. `db.upsert_match`
  also skips a duplicate stage number defensively. Do not revert to
  `stage_number`.

**Automated discovery via Algolia** (`match_search.py`; spiked live
2026-07-19):
- PractiScore's match search is Algolia-backed and, unlike the site,
  `algolia.net` is NOT behind Cloudflare. The `postmatches` index (~342k
  records) lists completed matches; each has `match_id` (the UUID →
  `/results/new/{id}`), `match_date` ("YYYY-MM-DD"), `match_subtype`
  (`uspsa` is a facet — the USPSA filter), and `front_club_state` (2-letter,
  a facet — the state filter; the `state` field is empty here).
- The scoped Algolia key is short-lived; `capture_search_key` reads it from
  the site's own search request during one page visit (which also warms
  Cloudflare for the per-match fetches).
- `match_date` is NOT range-filterable; bound queries with `numericFilters`
  on `timestamp_utc_updated` (padded) + client-side `match_date` filter.
  Algolia pages only ~1000 hits/query, so discovery chunks the range into
  MONTHLY sub-windows and dedupes on `match_id`.
- Per-match RESULTS pages are still Cloudflare-fronted + JS-rendered, so
  fetching still needs the browser. Headless usually fails Cloudflare here,
  so the automated run tries headless briefly then reopens visible (which
  self-drives — you still never click matches).

**Site behavior:**
- Cloudflare fronts practiscore.com; robots.txt disallows crawling; staff say
  there is no API. Scraping is human-*triggered* (you set a date range and
  click Fetch), not human-*operated*: discovery uses the site's own public
  Algolia search at low volume, per-match fetches keep the ≥3s jittered
  delay + USPSA-only default, and no Cloudflare bypass is attempted.
- Results URLs come in variants: `/results/all/{id}`, `/results/new/{id}`,
  `/results/html/{id}`. The Web Report link is not on every view;
  `results_url_variants()` tries them in order. Live 2026 matches use UUIDs;
  older ones use numeric ids. Both work as `source_key`s.
- Search results mix regions. Reports are checked for `$INFO Region:` and
  non-USPSA (IPSC, SCSA…) are skipped by default (`--allow-non-uspsa` keeps
  them). Region is stored on the `matches` table.
- Failed report fetches save the body to `data/debug/{key}.html` plus a
  `{key}.json` sidecar (requested URL, HTTP status, final URL, page title).
  `python diagnose_debug.py` summarizes them. Diagnose from these files;
  never guess.

**Expected small-corpus dashboard states (not bugs):** with only 3 matches /
1 classifier code, the difficulty panel says "not enough classifier data"
(needs ≥2 distinct classifier codes, ≥3 classes each) and the trend-read
cards need ≥4 periods. These resolve as the corpus grows.

## Environment (this machine)

- Project root: `E:\Python_stuff\uspsa_test\uspsa-analytics`
- Venv: `.venv` (base Python 3.13 at
  `C:\Users\Anand\AppData\Local\Programs\Python\Python313\python.exe`)
- Fresh PowerShell needs:
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` then
  `.\.venv\Scripts\Activate.ps1` — confirm `(.venv)` in the prompt. Plain
  `python` without the venv hits the Microsoft Store stub and fails.
- A sibling project lives at `E:\Python_stuff\kepler_test` (Kepler transit
  analytics). NEVER mix files between the two — both use generic names
  (`dashboard.py`, `config.py`). Entry scripts here check
  `config.PROJECT_TAG == "uspsa-analytics"` and exit if the folder is
  cross-contaminated; `check_setup.py` diagnoses it.
- Test hooks: `PS_SEARCH_URL` (point the scraper at a mock server),
  `PS_CHROMIUM_PATH` (alternate browser binary), `--headless`,
  `DATABASE_URL` (e.g. `$env:DATABASE_URL='sqlite:///C:/temp/t.db'`).
  No mock server ships in the repo; write one against these hooks if needed.

## Invariants — never break these

1. The credential-free reviewer path must always work on a fresh clone:
   `pip install -r requirements.txt` → `python scrape.py --reparse-only` →
   `streamlit run dashboard.py`. No login, no scraping — with an empty
   `data/raw_reports/`, ingestion falls back to the tracked
   `data/sample_reports/` matches. Keep those 3 files tracked.
2. No credentials anywhere in the repo, README, or committed files — no
   shared accounts, no `session_state.json` in git (see `.gitignore`).
3. Scraping stays polite and human-*triggered*: default ≥3 s jittered
   delay, no Cloudflare bypass attempts, USPSA filter by default. The
   dashboard shows a match count + ETA before a run so large fetches are
   deliberate; runs are resumable (cached matches skip). No hard cap.
4. Ingestion stays idempotent (keyed on `source_key`); re-runs replace, never
   duplicate.
5. Local dashboard port 8531 is set via `--server.port 8531` (avoids the
   sibling kepler project's 8501), NOT in `.streamlit/config.toml` — a
   hard-coded `server.port` there breaks Streamlit Community Cloud deploys
   (the platform assigns its own port). Keep config.toml port-free.
6. `seed_demo.py` output stays clearly labeled synthetic.

## How to test changes

After touching parser/db/analytics:
1. `python -m py_compile *.py`
2. `python report_parser.py data\reference\web_report_samples\162570.txt`
   — expect 0 skipped lines, 0 HF sanity violations. (For the embedded
   parser: `python embedded_parser.py <saved-page-data>.json`.)
3. `$env:DATABASE_URL='sqlite:///C:/temp/t.db'; python scrape.py --reparse-only`
   — with an empty `data/raw_reports/` this ingests the TX demo (32
   matches, 7,482 scores, 0 HF flags); with a live corpus it mirrors that.
4. Same env, boot `streamlit run dashboard.py` and click through all 3 tabs.
5. `python check_setup.py` must end READY.
After touching `match_search.py`: `python -m pytest test_match_search.py`
(pure helpers; no network). Then a live smoke: `python scrape.py
--start-date <a> --end-date <b> --state TX --discover-only` should write
`data/pending_matches.json` with a match count.

## Prioritized tasks

1. **Build the corpus via the dashboard.** "⚡ Fetch live data" panel: set
   a date range (+ optional state) → Find matches → Fetch. Large national
   ranges are thousands of matches / multi-hour; use a state filter or
   narrow window to start. `HF sanity flags` must stay 0 across the corpus.
   (Live embedded path already verified on real USPSA matches.)
2. **Session persistence — DONE (2026-07-19).** `scrape.py` uses
   `launch_persistent_context(data/browser_profile)`, so Cloudflare
   clearance (and any optional login) survives across runs;
   `--fresh-profile` wipes it. The profile dir is credential-equivalent
   and gitignored. Do not re-implement via storage_state.
3. Optional: extend `data/reference/classifier_titles.csv` for any new
   classifier codes the corpus surfaces; Postgres swap is already documented
   in README.
4. Optional refinement: `fetch_panel.py` polls via `time.sleep`+`st.rerun`,
   which hides the charts during an active fetch. `st.fragment(run_every=)`
   would let charts stay visible — a nice-to-have, not required.

## Where knowledge lives

`README.md` — quick setup/run guide for reviewers (start here).
`METHODOLOGY.md` — verification record, methodology math, schema, deep dive
(the former README; scraping-workflow sections predate the automated path).
`report_parser.py` — Web Report text field-position evidence in comments.
`embedded_parser.py` — embedded-JSON field mapping + reconciliation logic.
`match_search.py` — Algolia `postmatches` query strategy (chunking, filters).
`fetch_panel.py` — dashboard fetch UI (subprocess + progress-file polling).
`docs/superpowers/specs/2026-07-19-embedded-json-ingestion-design.md` and
`…-automated-date-range-scraping-design.md` — why those paths exist + how
they were validated.
This file — everything above. Update it when facts change.
