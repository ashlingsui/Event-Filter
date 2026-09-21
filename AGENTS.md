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
- Do not run `supabase/apply_schema.py`. Its SSL context disables certificate and
  hostname verification. Use a separately reviewed, TLS-verifying approach if schema
  work is later authorized.
- Do not run live Supabase scripts or tests without explicit authorization and valid,
  safely configured credentials.

## Git discipline

- Stage intentionally with explicit paths; never use `git add .` for a baseline.
- Inspect the staged diff and run a secret scan before every commit.
- Do not rewrite history, force push, or discard existing work unless explicitly asked.
