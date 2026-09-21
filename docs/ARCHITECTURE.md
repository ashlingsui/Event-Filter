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

- `prototype.html`, `design_v2.html`, and `design_v3.html` are standalone static interface
  artifacts; there is no served frontend application in this repository.
- `supabase/` contains a SQL schema and Python REST/onboarding/migration helpers for a future
  hosted backend. The local pipeline does not depend on a live Supabase connection.
