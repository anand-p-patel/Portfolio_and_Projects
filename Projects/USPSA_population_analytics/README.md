# USPSA Population Analytics
Demo dashboard: https://dashboardpy-w4tyhzptkdjqizn9fzjgsq.streamlit.app/

Turn public [PractiScore](https://practiscore.com) match results into two questions worth answering:

- **Which shooting divisions are growing or shrinking** over a time frame you pick (Carry Optics, Limited, Open, …).
- **How hard is each classifier stage, really** — a skill-adjusted difficulty score that separates *who showed up* from *how tough the stage was*.

It scrapes the data itself (no account needed), loads a SQL database, and serves an interactive dashboard.

---

## Run it in 60 seconds — no account, no scraping

Real USPSA match data ships with the project, so everything runs end-to-end straight from the download. You need **Python 3.11+** and nothing else.

```bash
pip install -r requirements.txt
streamlit run dashboard.py         # opens in your browser (http://localhost:8501)
```

That's it — two commands. The dashboard builds its database from the bundled demo on first launch, so your browser opens to a working app with a real month of Texas USPSA data — **32 matches, 1,344 entries, 7,482 stage scores** across June 2026. Click through the three tabs and play with the filters in the sidebar.

> On Windows PowerShell, if `python` isn't found, use the launcher: `py -3` in place of `python`.
> Prefer to load the database explicitly first? Run `python scrape.py --reparse-only` before launching — the dashboard does the same thing automatically.

---

## Pull fresh data yourself (optional)

Want more than the bundled matches? The dashboard can scrape live results for any date range — **fully automated, still no login required.**

1. Install the browser once: `playwright install chromium`
2. In the dashboard sidebar, open **⚡ Fetch live data**, pick a date range (and optionally one state), and click **Find matches**.
3. It shows how many USPSA matches it found and roughly how long they'll take. Click **Fetch**, watch the progress bar, then **Reload data**.

A browser window may pop up to clear a one-time Cloudflare check — you don't have to click through matches or type anything; it drives itself. Big date ranges (a whole year, nationwide) can be thousands of matches and take hours, so starting with one state or a narrow window is the easy way in. Runs are resumable — stop and re-fetch anytime.

---

## Deploy the dashboard (Streamlit Community Cloud)

Point [share.streamlit.io](https://share.streamlit.io) at this repo with `dashboard.py` as the entry point — no secrets or extra config needed. On first load the app self-populates from the bundled sample matches, so the hosted demo is never blank.

**The live-fetch panel is automatically hidden on hosted deploys** and replaced with a short notice. That's by design, not a limitation of the scraper: PractiScore sits behind Cloudflare, which blocks cloud-datacenter IPs, and hosted platforms have no browser to drive. Scraping is a **local** capability — clone the repo, `playwright install chromium`, and the fetch panel appears and works. The hosted app is the analytics showcase; your machine is the data-collection tool.

---

## What you're looking at

| Tab | Question it answers |
|---|---|
| **Division trends** | Is Carry Optics really taking over? Who's gaining or losing share of the field, and how fast? |
| **Classifier difficulty** | For each classifier stage, how did every skill class (GM → U) do — and which stages were hard for *everyone*, not just the slow shooters? |
| **Data & methodology** | The sample size behind each number, and how the difficulty math works. |

The difficulty score is the clever bit: it z-scores each skill class against itself, so a stage that every class shot below their own average is flagged as genuinely hard — not just a stage that happened to draw slower shooters. Full math in **[METHODOLOGY.md](METHODOLOGY.md)**.

---

## How it works (the 10-second version)

```
match_search.py ─► scrape.py ─► data/raw_reports/ ─► ingest.py ─► db.py ─► analytics.py ─► dashboard.py
 find matches       fetch their    match JSON /        parse to      SQLite    pandas +         Streamlit
 by date (Algolia)  results pages  text reports        one contract  (Postgres)  Z-scores       + Plotly
```

The data comes straight out of each match's **public results page** — PractiScore renders the full match into the page itself, so no login is needed. Match *discovery* uses PractiScore's own search index to list matches by date. Every scraped hit factor is cross-checked against its own scoring math, so a bad parse gets flagged loudly instead of quietly corrupting the numbers.

Deeper dive — the parsing, the scraping strategy, the schema, and how it was validated against 49 real reports (126,629 score rows) — lives in **[METHODOLOGY.md](METHODOLOGY.md)**.

### Project map

Each layer is one focused module, wired in the order above:

| Role | Files |
|---|---|
| **Discovery** | `match_search.py` — queries PractiScore's Algolia index for USPSA matches by date |
| **Scraping** | `scrape.py` — drives the browser, fetches each results page; `fetch_panel.py` — the dashboard's fetch UI |
| **Parsing** | `embedded_parser.py` (embedded JSON, primary) and `report_parser.py` (Web Report text, fallback) → one shared contract |
| **Storage** | `ingest.py` — parse-and-load (Phase C); `db.py` — SQLAlchemy schema |
| **Analytics** | `analytics.py` — participation trends + the skill-adjusted Z-score difficulty |
| **Presentation** | `dashboard.py` — the Streamlit app (entry point) |
| **Shared / tools** | `config.py` (constants, paths), `check_setup.py` (preflight), `diagnose_debug.py`, `seed_demo.py` |

---

## Troubleshooting

- **`python check_setup.py`** runs a preflight check (Python deps, browser, database) and tells you exactly what's missing.
- **Dashboard is empty?** It should self-populate on first launch; if not, run `python scrape.py --reparse-only` to load the bundled matches, then click **Reload data**.
- **No ⚡ Fetch panel?** That's expected on a hosted deploy — live scraping runs locally only. Install the browser (`playwright install chromium`) to enable it on your machine.
- **Live fetch finds nothing?** Make sure your date range actually contains matches; try a wider window or drop the state filter.

## Requirements

Python 3.11+. Everything installs via `pip install -r requirements.txt`. The database is a zero-setup SQLite file by default; point `DATABASE_URL` at PostgreSQL if you'd rather (see [METHODOLOGY.md](METHODOLOGY.md)).

## Credits

Classifier code/title reference and the bundled sample reports come from [`kmcken/CompetitionShootingAnalytics`](https://github.com/kmcken/CompetitionShootingAnalytics) (Apache-2.0).
