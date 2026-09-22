# Prep — specification

Written 2026-09-22. Extends `DESIGN_V12_HANDOFF.md` §3 (Prep) and `SPEC.md`.
Prep is generated **on a yes**, never for every scanned event.

---

## Why prep is not a side feature

Every event Ashling rated well, she arrived with a prior hook — she followed the speaker,
or already used the product. Every dud, she showed up cold. And the entire payoff of her
first logged event happened **in the queue, before doors opened**, because the pre-event
brief had told her the value window was *before*.

`LESSONS.md` #12 and #26: scoring picks the room, the brief is what converts it.

---

## §1 WHAT A BRIEF PRODUCES — four outputs, in priority order

### 1. Value window — *when* in this event the value happens

The highest-leverage output in the product, and the one nothing else has.

```
value_window   before | during | after | specific_block
rationale      one sentence, derived from format + schedule + hard stops
```

Examples: a hard-stop lunch event → *before* (no post-event mingle; arrive early).
A hackathon → *specific_block* (the demo hour). An evening mixer → *after*.

This is derivable from data already held — format, start/end, duration — and needs no
research. It ships first.

### 2. The hook — a line she can say, not a fact she must convert

"You've used OpenRouter since the build night" is a hook.
"The speaker is Head of Data at OpenRouter" is homework.

A hook must be **grounded in something true about her or about a sourced claim**, and it
must be phrased as speech, not as a dossier entry.

### 3. Who to look for

Not a guest list — those aren't obtainable. Three things that are:

- speakers and hosts, resolved (see §2);
- **anyone already in her `contacts` likely to be present** — a join against her own data.
  This is the operationalized form of the strongest pattern in her record: her contacts
  form where there is *recurring context*, not at one-off encounters;
- people on her watchlist associated with this host or calendar.

### 4. Exit condition — what makes this trip a success, decided before she goes

```
success_condition   free text, set by her, pre-event, immutable after start
```

"One conversation with someone at a scaled company." "See three demos."

An event with no success condition never ends — it stays open and gets re-litigated. This
also feeds the T+7 check: it is the question already asked, in her own words.

---

## §2 EXTERNAL RESEARCH — allowed, constrained

Research is **required**, not optional: her own record is empty for most events, so without
it a brief degrades to the event's marketing copy. Constraint, not removal.

### The governing rule

> **A claim without a source URL and a fetched-at timestamp does not render as a fact.**

Unsourced material renders as `pending`, visibly. The brief must remain useful with every
research field pending, because sometimes it will be.

### Identity resolution is a separate, gated step

The dangerous failure is not "what does this person do." It is **"is this the right
person."** Names collide; a confident wrong resolution produces a brief about a stranger,
and she walks up to someone referencing a career that isn't theirs. That is worse than no
prep at all.

```
identity_status   resolved | ambiguous | not_found
identity_evidence what tied the name to this profile (employer match on the listing,
                  the host's own link, a byline) + URL
```

- `resolved` requires corroboration from something tied to *this event* — the listing names
  their employer, the host links their profile, the speaker is on the host's team page.
- A name match alone is **never** sufficient.
- `ambiguous` renders as *"couldn't confirm which person this is"* and **no claims attach**.
  Never guess and never blend two candidates.

### Scope the research to three questions, nothing more

Not "tell me about this person" — that invites a biography and invites invention.

1. **What do they currently do, and where?** → also an input to `target_proximity`
2. **What have they said publicly and recently?** → hook material
3. **Is there anything connecting them to her?** → shared school, employer, prior event, mutual

Each answerable with a citation, or explicitly not answered.

### Freshness

Every claim carries `fetched_at`. A title can be two years stale; "Head of Data at X" is a
claim about *now*. Claims older than ~90 days render with their date visible.

---

## §3 RESEARCH PEOPLE, NOT EVENTS

Cache keyed on resolved identity, not on the event.

A speaker appearing at three events is researched **once**. This makes cost sublinear,
and — more importantly — it is the same store the **watchlist** needs. The watchlist was
always going to accumulate passively from scanned speaker names; research is what makes
those entries substantive rather than a list of strings.

One table serves prep and the watchlist. Build it once.

---

## §4 DATA SHAPE

```text
people                                  -- researched entities, cached, reused
  id
  display_name
  identity_status                       -- resolved | ambiguous | not_found
  identity_evidence[]                   -- {claim, url, fetched_at}
  current_role, current_employer        -- each with source_ref
  recent_public[]                       -- {summary, url, fetched_at}
  connection_to_user[]                  -- {kind, detail, url?}
  researched_at, research_cost_tokens

event_people                            -- join: who is at which event, and how we know
  event_id, person_id
  role                                  -- speaker | host | organizer | likely_attendee
  source_ref                            -- where this association came from

event_preparation
  event_id
  value_window                          -- before | during | after | specific_block
  value_window_rationale
  hook                                  -- {line, grounded_in, source_ref?}
  success_condition                     -- set by her, pre-event
  known_contacts[]                      -- join against her own contacts
  research_status                       -- pending | sourced | reviewed
  generated_at
```

`prior_history` is **derived at read time, never stored** — has she attended this host or
series before, and what happened. It changes as her record grows; a stored copy goes stale.

---

## §5 GENERATION & COST

- Generated **on a yes** (Want / GO), never for all ~100 scanned events.
- Research runs **server-side**, holding the key; never in the browser.
- Person-level cache means the marginal cost of a brief falls as her ecosystem repeats —
  which it does, because depth-over-breadth is the strategy.
- Under multi-user, `people` rows are **shared** (public figures, public claims, no personal
  judgments). `event_preparation` and `known_contacts` are **private per user**. This follows
  `SPEC.md` §4 exactly: shared facts pool, personal context never does.

---

## §6 BUILD ORDER

1. **Value window + exit condition.** No research needed; derivable today. Ships first and
   is already most of the value.
2. **`people` + `event_people` tables**, populated from the speaker names already extracted.
   No research yet — just the structure and the watchlist feed.
3. **Identity resolution**, with `ambiguous` rendering correctly. Gate everything else on this.
4. **The three research questions**, cited.
5. **Hook generation**, grounded in resolved claims and her own record.

Steps 1-2 are independent of the research pipeline, so the prep **screen** can be built
against this schema before any research exists — it renders pending states, which
`DESIGN_V12_HANDOFF.md` already requires.

---

## §7 WHAT MUST NEVER HAPPEN

- A host bio, speaker bio, or attendee claim with no source.
- A resolved identity on a name match alone.
- Two candidate people blended into one profile.
- A brief that reads as confident when `research_status = pending`.
- Research triggered for events she has not said yes to.
