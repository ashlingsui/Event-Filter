# Event Filter — shared instructions

This is the canonical cross-agent and cross-session instruction file. `CLAUDE.md`
imports it so Claude Code and Codex work from the same rules.

## Start of every session

1. Read this file, then `CURRENT_STATE.md` and `docs/ARCHITECTURE.md`.
2. Read `SPEC.md` before changing product behavior. Its outcome taxonomy and frozen
   definitions must not be redefined.
3. Check `git status --short` before editing. Preserve unrelated user changes.
4. Run `scripts/check.sh` before handing off a code or documentation change.

## Project conventions

- The local pipeline is staged: ingest, enrich, score, then capture. Do not blend
  responsibilities across stages or silently fill unknown data.
- `data/events.json` is a bare event array. `data/score_summary.json` stores
  score aggregates separately.
- Free text is the capture input; recorded facts and suspected hypotheses remain
  separate. Never make the frozen outcome definition or capture horizons adjustable.
- Keep `docs/ARCHITECTURE.md` descriptive of the system as it exists today. Put
  handoff status in `CURRENT_STATE.md`, not in the architecture document.

## Secrets and Supabase safety

- Never print, echo, read aloud, paste into logs, or commit credential values.
- Keep `supabase/.env` ignored. Verify it with `git check-ignore -v supabase/.env`
  before staging when relevant.
- `SUPABASE_SERVICE_ROLE_KEY` in `supabase/.env` is malformed. Do not correct it,
  rotate credentials, or otherwise modify credentials without explicit user approval.
- `supabase/apply_schema.py` now verifies TLS properly (fixed 2026-09-21). It trusts the
  system roots plus Supabase's published CA, and refuses to connect if the context is not
  fully verifying. It requires `supabase/prod-ca-2021.crt` (public certificate, downloaded
  from Project Settings -> Database -> SSL Configuration) and exits with instructions if
  it is absent.
- Never reintroduce `check_hostname = False` or `verify_mode = CERT_NONE` anywhere. The
  earlier justification — "schema.sql is non-secret DDL" — was wrong: that connection
  authenticates, so the database password crosses it. An unverified channel carrying a
  credential is never acceptable, regardless of how public the payload is.
- Running it still requires explicit user authorization and valid credentials.
- Do not run live Supabase scripts or tests without explicit authorization and valid,
  safely configured credentials.

## Git discipline

- Stage intentionally with explicit paths; never use `git add .` for a baseline.
- Inspect the staged diff and run a secret scan before every commit.
- Do not rewrite history, force push, or discard existing work unless explicitly asked.
