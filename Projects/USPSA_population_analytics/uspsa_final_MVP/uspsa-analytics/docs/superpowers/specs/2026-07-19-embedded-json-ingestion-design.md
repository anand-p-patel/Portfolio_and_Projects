# Embedded-JSON ingestion from public results pages — design

Date: 2026-07-19. Status: approved (approach A).

## Why

Live Web Report downloads (`/reports/web/{uuid}`) require a signed-in
PractiScore session (confirmed 2026-07-19: three matches, HTTP 200,
redirect to `/login`). But the *public* results pages embed the complete
match dataset as inline JavaScript — verified by loading
`/results/new/008ddac5-a1db-457c-8ed3-77f45eee3834` in the real browser
and inspecting all 89 network responses (no S3/JSON data fetch; the data
is server-rendered into the page):

- `matchDef = {...}` — name, date, `match_subtype` (uspsa/ipsc/sc...),
  club, level, `match_shooters` (division `sh_dvp`, class `sh_grd`,
  power factor `sh_pf`, DQ `sh_dq`, member `sh_id`), `match_stages`
  (`stage_classifier`, `stage_classifiercode`, `stage_scoretype`).
- `scores = {...}` — raw per-stage `stage_stagescores` (times, hits).
- `results = [...]` — precomputed standings: `results[0]` match-level
  (rank/percent/points per division and combined), `results[i>=1]`
  per-stage rows with `details` = A/C/D/M/NS counts, `Time`, `HF`
  (4 decimals), stage points (`result`), place (`rank`).

So the whole pipeline can run with no login. Login becomes optional,
only powering the legacy Web Report fallback.

## Decisions (user-approved)

1. Raw artifact = **both**: `data/raw_reports/{key}.json` (the three
   blobs verbatim + a `meta` block: source URL, fetch timestamp) is the
   parse source; `data/raw_html/{key}.html` is archival insurance
   (gitignored — regenerable, ~400 KB each).
2. Phase B = **embedded primary, Web Report fallback**: if the embedded
   variables never populate, the existing login-dependent report-link
   logic runs unchanged and saves `.txt`.

## Architecture (approach A — new sibling parser)

- **`embedded_parser.py` (new)**: `parse_embedded(data) -> (parsed,
  stats)` with the exact `report_parser.parse_report` output contract
  (`{match, stages, competitors, scores}`), so `db.py`, `analytics.py`,
  `dashboard.py` are untouched. Knows nothing about Playwright or files.
- **`scrape.py`** (Phase B only): after loading a results page, poll
  briefly (~10 s) until the page JS variables are objects, then
  `page.evaluate("() => ({matchDef, scores, results})")` — no HTML
  regex. Region check via `match_subtype` keeps the USPSA-only default
  (`--allow-non-uspsa` unchanged). Console banner demotes login to
  optional.
- **Phase C `ingest_raw_reports`**: glob `*.json` + `*.txt`, route by
  extension. If both exist for one `source_key`, `.json` wins with a
  warning.
- **`.gitignore`**: add `data/raw_html/`.

## Field mapping

| target | source |
|---|---|
| match.name/date/club/level | `match_name`, `match_date`, `match_clubname` + `match_clubcode`, `match_level` |
| match.region | `match_subtype` mapped (uspsa→USPSA, ipsc→IPSC, sc→SCSA, ...) |
| stage.number/name/scoring | `stage_number`, `stage_name`, `stage_scoretype` |
| stage.is_classifier/code | `stage_classifier`, `stage_classifiercode` |
| competitor identity | `sh_fn`, `sh_ln`, member number from `sh_id`/`sh_num` if >0 else None (IPSC sample had none — expected present on real USPSA matches, the open risk); comp# = 1-based index; join key internally is `sh_uid`↔`shooterId` |
| competitor attrs | division `sh_dvp` (normalized like report_parser), class `sh_grd`, PF `sh_pf`, DQ `sh_dq` |
| competitor match result | `results[0]` row: points `result`, place `rank` (division) |
| score row (per stage) | `results[i]` row: A/C/D/M/NS (+B where present) from `details`, procedurals `P`, `Time`, `HF`, stage points `result`, place `rank` |
| DNF | derived, same rule as before: no time AND no points AND no HF, or shooter absent from that stage's rows. Never from a single flag. |

## Integrity checks

Scoring values are NOT hardcoded: `matchDef.match_pfs` ships the exact
table per power factor (verified in the sample: Major A5/B4/C4/D2,
Minor A5/B3/C3/D1, M/NS −10). Look up the shooter's `sh_pf` row.

The `results.details` block carries A/C/D/M/NS/Time/HF but NOT
procedurals (those are encoded in the raw `scores` blob's target-type
arrays and are painful to decode). So both `total_points` and
`procedurals` are *reconciled*:

- `net_points = round(HF × Time)` (net is what report_parser stored as
  total_points; HF == net/time holds exactly in the text corpus).
- `gross = A·Av + C·Cv + D·Dv − 10·M − 10·NS` from the PF table.
- `implied_penalty = gross − net_points`. A clean non-negative multiple
  of 10 → `procedurals = implied_penalty / 10`, `penalties =
  implied_penalty`. Negative beyond tolerance, or not ~a multiple of 10
  → **`hf_sanity_violation`**: our A/C/D or major/minor mapping is
  wrong. Same contract as before: must stay 0 across the corpus;
  nonzero means investigate, never suppress. This single computation is
  both the integrity check and the procedural recovery.

`total_points` stored = `net_points`.

## Verification

1. **DONE** — Parse the saved probe page (10 shooters, 8 stages, IPSC):
   80 scores, 0 skipped, **0 HF sanity violations**. The zero-violation
   result is strong internal validation: for every scored row the hit
   counts (A/C/D/M/NS via the match's own `match_pfs` table) reconcile
   with HF×Time to a clean multiple of 10, proving the field mapping and
   major/minor selection are correct.
2. **DONE, finding** — Numeric-ID (older) matches do NOT serve embedded
   JSON. `/results/new/162570` bounces to a scores-search page;
   `/results/html/162570` is a static HTML `<table>` with `matchDef`
   present only as an empty stub. The extraction guard correctly
   rejects it and falls through to the Web Report fallback. So the
   "same match, both parsers" cross-check is not achievable — no match
   exposes both a public embedded payload AND a login-free web report.
   The 3 bundled 2022 matches stay on the `.txt` path (already
   ingested); the embedded path serves the modern (UUID) matches the
   user harvests going forward.
3. **DONE** — Live USPSA match `06e7f238-…` (Gun Craft Practical
   Shooters, 2026-07-19): 65 shooters, 7 stages, 448 scores, 0 skipped,
   0 HF sanity violations. Member numbers 61/65 (real USPSA formats),
   classes B–M+U, six real divisions, both power factors, one classifier
   stage (20-02) with procedurals reconciled. Open risk closed.
4. **DONE** — Reviewer path regression: py_compile clean; `--reparse-only`
   → 3 matches / 1,094 entries / 13,568 scores (unchanged). Remaining:
   dashboard click-through, `check_setup.py` READY, mock-server pass
   (`PS_SEARCH_URL`) before the first live harvest.

## Invariants preserved

Credential-free reviewer path untouched (bundled `.txt` +
`report_parser.py`); no credentials in repo; polite human-driven
scraping (same delays, still one page load per match); idempotent
ingestion on `source_key`; port 8531; synthetic data labeling.
