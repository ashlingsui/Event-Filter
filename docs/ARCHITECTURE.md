# Current architecture

## Local event pipeline

Python entry points execute a file-backed pipeline rooted at the repository:

1. `run_ingest.py` fetches Luma, Haas CampusGroups, and Partiful sources defined in
   `config/calendars.json`. Source adapters in `ingest/` normalize them into the frozen event
   row shape in `ingest/schema.py`, then merge and write `data/events.json`.
2. `enrich_events.py` enriches those rows. `enrich/geocode.py` derives coordinates, nearest-BART
   walking time, and reachability using the BART station configuration and a local geocode cache.
   `enrich/llm_enrich.py` and `enrich/speakers.py` optionally use an Anthropic API key supplied
   through the process environment; without it, their judgment-based fields remain unknown.
3. `score_events.py` calls `score/scorer.py` for value/cost estimates and `score/verdicts.py` for
   weekly quota, reachability, conflict, and reason-code policy. It updates `data/events.json`
   and writes aggregate output to `data/score_summary.json`.
4. `capture_feedback.py` and `run_checks.py` support outcome capture. `capture/` persists
   outcomes in `data/outcomes.json` and pending hypotheses in `data/pending_hypotheses.json`.
   T+7/T+30 recognition checks are derived from those local records.

## Configuration and stored data

- `config/bart_stations.json` supplies the static station set.
- `config/weekly_quota.json` provides per-week score-policy overrides.
- `data/` holds local event, enrichment-cache, score, outcome, and hypothesis records.

## Interfaces

- `prototype.html` and `design_v2.html` through `design_v12.html` / `Dark_v1.html` are static
  design references, not the built product. `design_v12.html` is the current visual reference;
  `DESIGN_V12_HANDOFF.md` is its implementation contract.
- `app/` is the real frontend, built against local data only, one route at a time per
  `DESIGN_V12_HANDOFF.md`'s sequence. It is a static, dependency-free HTML/CSS/JS app — no
  build tool, no framework, no bundler — so it keeps `DESIGN_BRIEF.md`'s "no server, opens
  anywhere" requirement: every script is a plain `<script>` tag, not an ES module, because
  `file://` blocks module imports.
  - `app/build_data.py` reads `data/events.json`, `data/score_summary.json`,
    `data/outcomes.json`, `data/pending_hypotheses.json`, and
    `app/config/social_cohort_overrides.json`, and writes `app/generated/data.js` (a baked
    `window.EVENT_FILTER_DATA` snapshot). It only reads from `data/` and `app/config/` and
    only writes into `app/generated/`; it never rewrites `data/events.json` and never touches
    `ingest/`, `enrich/`, `score/`, or `capture/`. Re-run it after every pipeline run.
  - `app/data_access.js` is the single data-access module every view reads through. Swapping
    the local snapshot for a live Supabase backend later means rewriting this one file.
  - `app/build_data.py` also drops any event confidently outside California entirely (not
    shown, not counted — not even in the suppressed line), per Ashling's 2026-09-21 call: an
    out-of-state or international row on this local pipeline's calendars isn't a solvable-
    friction "suppressed" case, it's categorically not happening. Confident means real lat/lng
    outside a California bounding box, or a "`<City> |` title" prefix that names a recognized
    non-California city; a row with neither signal is left in (SPEC.md's missing-data policy —
    unknown is not false — applies to exclusion decisions too). `score_summary.json`'s raw
    suppressed total still includes these rows (it's the pipeline's own unmodified output); the
    board shows a recomputed California-only total instead so the displayed number matches what
    a click into the drawer can actually show.
  - `app/config/social_cohort_overrides.json` is a small, explicitly human-curated, mostly-
    empty allowlist of event ids to show in the board's Social/Cohort lane. It exists because
    `score/verdicts.py` has no field distinguishing a social/cohort plan from an ordinary
    low-scoring professional event, and a per-club or per-format rule doesn't work (the same
    club and the same `mixer` format cover both a happy hour and a professional panel in real
    data). See the file's own `_note` — its current entries are Claude's draft guesses, not
    confirmed by Ashling, and unlisted events always keep their real pipeline verdict.
  - For local preview, `.claude/launch.json` runs `python3 -m http.server` over `app/` — that
    server is a development convenience only, not a product requirement; the shipped page
    still opens directly from disk with no server.
- `supabase/` contains a SQL schema and Python REST/onboarding/migration helpers for a future
  hosted backend. The local pipeline does not depend on a live Supabase connection.
