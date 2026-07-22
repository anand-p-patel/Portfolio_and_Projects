# USPSA Population Analytics Engine v2

> **For setup and how to run, see [README.md](README.md).** This document is the
> technical deep dive — architecture, the difficulty math, and how each layer
> was verified.

A pipeline that turns PractiScore match results into two analyses:

1. **Division trends over time** — Carry Optics, Limited, Limited Optics, and Open participation (counts and share of the whole field) across a time frame you select.
2. **Classification vs classifier difficulty** — for every classifier stage (`99-11`, `03-05`, ...) found in your data, how GM/M/A/B/C/D/U shooters performed, plus a skill-adjusted difficulty score per classifier.

```
match_search.py ─► scrape.py ─► data/raw_reports/ ─► ingest.py ─► db.py ─► analytics.py ─► dashboard.py
 Algolia index      Playwright    *.json (embedded)   parse to    SQLite/     pandas+Z      Streamlit
 (find by date)     fetch pages    *.txt  (fallback)  contract    Postgres    scores        + Plotly
```

Two parsers feed one contract. The **primary** source is the JSON every public
results page renders into itself (`embedded_parser.py`); the **fallback** is the
older plain-text "Web Report" for pages that don't embed it (`report_parser.py`).
Both emit the identical `{match, stages, competitors, scores}` structure, so the
database and everything downstream never know which was used. `ingest.py` owns
the parse-and-load step (Phase C) and imports no browser code, so the dashboard
reuses it to self-populate the database on first launch — no manual load step,
and a hosted deploy is never blank.

## Quickstart — no account, no scraping, real data

Nothing here requires a PractiScore login or any credentials. A real month
of Texas USPSA matches (June 2026) ships in `data/sample_reports/` (used as a
fallback whenever your live corpus is empty), so the pipeline and dashboard
run end-to-end on genuine data straight from the download:

```bash
pip install -r requirements.txt
python check_setup.py            # preflight: folder, deps, browser, DB
python scrape.py --reparse-only  # parse the bundled REAL demo -> SQL
streamlit run dashboard.py       # opens in your browser (http://localhost:8501)
```

That's 32 matches, 1,344 competitor entries, and 7,482 stage scores (0 HF
sanity flags) — enough to exercise every chart with real trends and classifier
difficulty. For a synthetic long-horizon season instead, `python seed_demo.py`
builds an 18-month demo (clearly labeled synthetic in the dashboard; its trends
are invented and must not be presented as real).

Live scraping is an optional extra step for building your own larger corpus —
see below. It is never required to review, run, or evaluate this project.

## Live-data workflow (automated, no login)

Building your own corpus is a two-click flow in the dashboard's **⚡ Fetch live
data** panel — pick a date range (and optionally one state), **Find matches**,
then **Fetch**. No account, no driving the search UI, no clicking matches.
Under the hood:

1. **Discover** — `match_search.py` queries PractiScore's Algolia `postmatches`
   index for USPSA matches whose date falls in the range. That index is public,
   lives on `algolia.net` (not behind Cloudflare), and returns each match's
   UUID, date, subtype, and club state. A wide range is chunked into monthly
   sub-queries to stay under Algolia's ~1,000-hit page limit, then deduped.
2. **Fetch** — `scrape.py` opens each match's public results page and reads the
   match JSON the page renders into itself (see *Why it's built this way*),
   with a jittered ~3 s delay between matches. Files land in
   `data/raw_reports/*.json`, cached, so re-runs only fetch what's new — a long
   run that's interrupted resumes on the next click.
3. **Load** — every file is parsed and ingested into SQL; ingestion runs in
   batches during the fetch so the dashboard fills in as it goes. Click
   **Reload data** to see it.

The same thing from a terminal, if you prefer:

```bash
playwright install chromium                                    # one-time
python scrape.py --start-date 2026-06-01 --end-date 2026-06-30 --state TX
python scrape.py --start-date 2026-06-01 --end-date 2026-06-30 --discover-only  # count only
```

Other flags: `--cap N` (test runs), `--refresh` (re-fetch cached), `--state XX`,
`--reparse-only` (rebuild the DB from cached files, no browser), and the older
interactive `python scrape.py` with no dates (you drive the search yourself).

## Deployment: a deliberate local/hosted split

The dashboard deploys to Streamlit Community Cloud with `dashboard.py` as the
entry point and no extra config. Two design choices make that clean:

- **Zero-config bootstrap.** The database (`data/uspsa.db`) is never committed.
  On first launch the dashboard calls `ingest.ingest_raw_reports()`, which loads
  the live corpus if present and otherwise falls back to the bundled
  `data/sample_reports/` — so a fresh clone or a hosted instance is always
  populated, never blank.
- **Scraping is local-only, on purpose.** `fetch_panel.scraping_available()`
  checks for an installed Playwright browser; a hosted instance has none (and
  PractiScore's Cloudflare layer blocks datacenter IPs regardless), so the
  live-fetch UI is replaced with a short notice there. Because `ingest.py`
  carries no browser dependency, the dashboard imports it freely while the
  Playwright code stays confined to `scrape.py` / `match_search.py`. The hosted
  app is the analytics showcase; data collection runs on a real machine.

## Why it's built this way

The data is read straight from each match's **public results page** — no login,
no separate API. PractiScore server-renders the whole match into three inline
JavaScript variables (`matchDef`, `scores`, `results`); the browser has already
parsed them, so `scrape.py` reads them back out and `embedded_parser.py` maps
them to the database contract. Scoring point values come from the match's own
power-factor table (`match_pfs`), and net points are reconciled against the
precomputed hit factor — that reconciliation *is* a per-row sanity check, so a
mis-mapped field is flagged loudly instead of corrupting a metric.

That approach was reached by ruling the alternatives out:

- **No official API, and hardening over time.** PractiScore staff state there is no API and no sanctioned scraping; a 2024 community thread documents direct `results.json` pulls that used to work now returning Access Denied ([community.practiscore.com, "Programmatically Pulling Scores"](https://community.practiscore.com/t/programmatically-pulling-scores/14836)). Older tools (`unibrain1/Parse_Practiscore`, `jeffersonjhunt/ppull`) pulled from the public S3 bucket `s3.amazonaws.com/ps-scores/production/{uuid}/…`; that path now returns 403. The site sits behind Cloudflare and its `robots.txt` disallows automated crawling.
- **The login-gated Web Report was the original plan, and is now the fallback.** The plain-text report (`practiscore.com/reports/web/...`) parsed by `report_parser.py` requires a signed-in session — anonymous GETs bounce to `/login`. It's kept only for the rare page that doesn't embed the JSON (e.g. very old numeric-ID matches, which render as static HTML tables). `report_parser.py`'s field positions were empirically verified against 49 real reports (see *How this was verified*), and its output is identical to the embedded parser's, so either source flows through the rest of the pipeline unchanged.

So the design leans into the one thing that is clearly fine: **reading public pages a person could open**, at low volume, with polite delays. Discovery uses the site's own public search index; the per-match fetches keep the jittered delay and USPSA-only default. Keep volumes reasonable and don't redistribute the raw data.

**Endpoint discovery, instrumented — and how the automated path was found.** The original blocker was identifying the real search/results endpoints. Rather than guess, the scraper logs every JSON response the site makes to `data/discovery_log.jsonl` (URL, status, top-level keys). Reading one session's log is exactly what surfaced the Algolia search backend (`api/v1/search/key` handing out a scoped key, then `*.algolia.net/1/indexes/*/queries` against a `matches`/`postmatches` index) — which became the automated, Cloudflare-free discovery layer in `match_search.py`. The instrument turned "which endpoint?" into "read the list of ones that actually fired."

## Database schema

Star-style layout, same shape as your PostgreSQL design: `matches` and `stages` act as dimensions; `competitors` (one row per registration, carrying division/classification/DQ) and `stage_scores` (one row per shooter per stage, carrying the hit factor) are the fact tables. SQLite is the zero-setup default; point `DATABASE_URL` at Postgres to use your existing backend:

```bash
pip install psycopg2-binary
export DATABASE_URL=postgresql+psycopg2://user:pw@localhost:5432/uspsa
python scrape.py --reparse-only     # reload cached reports into Postgres
```

Ingestion is idempotent — each match is keyed by `source_key` derived from its URL, and re-ingesting replaces that match's rows rather than duplicating them.

## Difficulty methodology (the Z-score layer)

Raw mean hit factor on a stage confounds *who showed up* with *how hard the stage is*. For each classification k, take its mean HF on every classifier c and z-score **within the class, across classifiers**: z(c,k) = (mean_HF(c,k) − μ_k) / σ_k. That removes class k's overall pace. The difficulty score is D(c) = −mean over k of z(c,k): positive means every class — GM and D alike — shot that stage below their own norm. Guards: a cell needs ≥ 5 valid runs (slider), a classifier needs cells from ≥ 3 classes (slider), a class column must span ≥ 2 classifiers (σ undefined otherwise), and DQ/DNF/zero-HF runs are excluded throughout.

`data/reference/classifier_titles.csv` maps codes to official names (e.g. `99-11`) so charts read as stages, not serial numbers.

## How this was verified

**The text (fallback) parser** was validated against a corpus of **49 real PractiScore web reports (10,497 competitors, 126,629 score rows, 2022 Level I–II USPSA matches)**: all 49 parse with zero skipped lines; hit factor equals total points ÷ time to four decimals in 100.0% of timed rows (fields 25/27/28 confirmed); the DQ flag is field 4 of E-lines (the only flag ever set for zero-point shooters) and field 3 of I-lines (all 3,057 set rows had zero HF and belonged to match-DQ'd shooters). The audit also caught a real bug inherited from the reference parser: **I-line field 4 is not DNF** — it's a near-constant per-match app flag that is "Yes" on ~60% of valid scores, and trusting it would have silently discarded most classifier runs. DNF is derived (no time, no points, no HF) instead of read.

**The embedded (primary) parser and the automated path** were verified live against the current site:

- A live USPSA match parsed end-to-end — 65 shooters, 7 stages, 448 scores, 0 skipped, **0 hit-factor sanity violations** (every scored row's hit counts reconcile with HF × time to a clean penalty multiple, using the match's own power-factor table). Real USPSA member numbers and GM–U classes came through; a classifier stage was detected and its difficulty math exercised.
- A **two-in-one match** — 8 stages that reuse display numbers `1,2,3,4,1,2,3,4` — surfaced a real bug (the stage numbers collided on the database's unique key). Stages are now keyed by their position in the results array, matching how score rows reference them, so such matches ingest cleanly. One odd match can never abort a corpus-wide run.
- **Automated discovery** was run against the live Algolia index: a one-week Texas query returned 14 USPSA matches with correct UUIDs and dates; a capped fetch downloaded and ingested them cleanly. The date-window chunking, USPSA/state facet filters, and hit → results-URL mapping are covered by unit tests (`test_match_search.py`).

**What depends on the live site:** the embedded JSON variables and the Algolia index shape are read at runtime, and failures are loud and per-match (a bad match is skipped and logged, never silently mis-parsed). Old numeric-ID matches don't embed the JSON and fall through to the Web Report path.

Three real reports ship in `data/sample_reports/`, so `python scrape.py --reparse-only` loads genuine match data with no browser at all.


## Troubleshooting a live run

**Nothing downloads / everything skips.** Read the per-match reason; each names its own cause.

| Message | What it means | Fix |
|---|---|---|
| headless blocked — reopening visible | Cloudflare challenged the headless probe (normal for this site) | Nothing — a visible window opens and self-drives; clear the one-time check if it appears |
| `skipping IPSC match` (or SCSA, IDPA…) | Correct behavior — the match isn't USPSA | Expected; the USPSA filter is doing its job (`--allow-non-uspsa` keeps them) |
| `no embedded match data on results page` | An old numeric-ID match that renders a static table, not the JSON app | Falls through to the Web Report path; signed-in sessions can still fetch it |
| Found 0 matches | The date range (or state) contains no USPSA matches with posted results | Widen the window or drop the state filter |
| `no Algolia key captured` | Cloudflare blocked the search-key request | Let the visible window open and clear the check; re-run |

Blocked per-match responses are saved to `data/debug/*.html` with a `.json` sidecar (requested URL, HTTP status, final URL). Run `python diagnose_debug.py` to summarize them — it classifies each page (Cloudflare / login wall / 404 / redirect / results page), follows any redirect, and flags files that are secretly valid reports.

**Wrong app opens / familiar filenames from another project.** This project uses ordinary names (`dashboard.py`, `config.py`, `analytics.py`) that other Python projects also use. If it shares a directory with another codebase, `streamlit run dashboard.py` can launch the *other* project's dashboard, and imports can cross-wire between the two. **One project per folder is the rule.** The safeguards: every entry script refuses to run if the `config.py` it finds isn't this project's (clear STOP message instead of a traceback), `python check_setup.py` names any file in the folder that belongs to a different project, and you can pin the dashboard to its own port locally with `streamlit run dashboard.py --server.port 8531` so it can't be confused with another Streamlit app on the default 8501. (The port is deliberately *not* set in `.streamlit/config.toml` — a hard-coded port there breaks Streamlit Community Cloud deploys.)

**Corpus vs. samples.** Your live scraped matches live in `data/raw_reports/` (gitignored); the three bundled reviewer matches live in `data/sample_reports/` (tracked) and are used only as a fallback when the live corpus is empty. `--reparse-only` mirrors disk — it prunes DB matches whose files are gone — so the database always reflects exactly what's in `raw_reports/`.

**Schema note:** if you have a database from an earlier build, delete `data/uspsa.db` and re-run `python scrape.py --reparse-only`.

## Attribution

Web-report field positions (as corrected here), the classifier code/title list, and the bundled real match reports come from [`kmcken/CompetitionShootingAnalytics`](https://github.com/kmcken/CompetitionShootingAnalytics) (Apache License 2.0). The bundled `classifier_titles.csv` is redistributed under that license.

## Study guide

Since the point of this project is that you can rebuild it: `match_search.py` is the reverse-engineered API client (a public Algolia index, date-window chunking, pure functions with unit tests); `scrape.py` is the asyncio + Playwright material (a headless-then-visible Cloudflare fallback, background progress to a status file); `embedded_parser.py` and `report_parser.py` are two takes on defensive parsing of an undocumented format into one shared contract; `ingest.py` is the browser-free seam between files and SQL (idempotent upserts, disk-mirroring prune, the dashboard's bootstrap); `db.py` is SQLAlchemy 2.0 ORM with cascading deletes; `analytics.py` is where the Z-score normalization lives — read `difficulty_scores` until you could derive it on paper; `dashboard.py` + `fetch_panel.py` are presentation and orchestration only, no math.
