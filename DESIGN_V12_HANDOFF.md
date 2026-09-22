# Event Filter v12 — implementation handoff

`design_v12.html` is the current frontend UX reference for the first build. It is a
working prototype, not production code or a replacement for `SPEC.md`.

## Read this first

Before implementing, read in this order:

1. `AGENTS.md` — shared safety and project conventions.
2. `SPEC.md` — frozen outcome taxonomy and product definitions.
3. `DESIGN_BRIEF.md` — product intent and voice.
4. This handoff and `design_v12.html` — screen behavior and visual direction.

Do not reinterpret a frozen outcome, make capture horizons configurable, or turn an
unknown into an inferred fact just to fill a screen.

## Product intent

This is a personal decision tool for professional events, not an event-discovery
dashboard. Its job is to make it easier to say no with a clear, reviewable reason,
then learn from outcomes over time.

The map-and-field-board look is an interaction surface: it should make a week's
decision landscape easy to scan. It should never make attendance limits, scores, or
social plans feel like surveillance or a productivity game.

Keep these ideas legible in the product:

- Professional events receive an evidence-based probability and an outcome such as
  `GO`, `PART`, `SKIP`, or conditional `GO_IF`, as defined in `SPEC.md`.
- Social/cohort plans are intentionally separate from professional outcomes. They are
  shared plans, not failed or unscored professional events.
- P means the pre-event chance of a meaningful professional outcome: either a
  traceable S2/S3 contact or a concrete build/progress signal. It is not a fun,
  prestige, or social-life score.
- Facts, source provenance, and hypotheses have different status and must stay visibly
  distinct.

The prototype uses four short decision principles. Preserve their wording:

> What decision does this event deserve?

> Strong room + real access. Go with intent.

> Interesting, but the outcome is not clear enough.

> Not everything good belongs on your calendar.

## Routes and interactions

### 1. Now / attention entry (`#/home`)

The default entry is a short answer to “do I owe anything, and is there anything to
decide?” It is not a replacement for the field board. It should show only actionable
work and route each action to its focused workflow:

- professional decisions ready for an intent/review;
- **Record event feedback** for read-backs due, tied to the exact event and capture
  horizon;
- a prep brief for an event already being attended.

State what does **not** need attention as well: settled skips retain their reasons on
the board, and social/cohort plans remain outside professional scores and read-backs.
Avoid turning this into a generic dashboard or an exhaustive week browser. The final
v12 treatment is deliberately lean: three equal-size action cards, each with only a
short label, action, count/status, and destination; followed by one quiet no-action
line for settled skips and social/cohort plans.

### 2. Decision board (`#/board`)

Show a chosen week's whole landscape, not only recommended events. The current v12
prototype has three scan groups:

- professional decisions (including Go and Part),
- social/cohort plans,
- skipped events.

Requirements:

- Every event in the selected week's data appears in the inventory. Skips may be more
  compact, but they cannot disappear.
- Every inventory row includes the concise reasoning sentence at list level. A person
  must be able to see why an event is Go, Part, Skip, or social without selecting it;
  selecting an event is for evidence and action, not permission to read the decision.
- Selecting an inventory row or map marker selects the same event and updates the
  adjacent detail panel.
- The adjacent panel must show, in this order: event name, address/location, one
  decision line, and a prominent score for professional events. It also exposes the
  event's original listing/source link and an event-detail action.
- Professional marker bubbles scale monotonically with P. V12 prototypes this with
  `radius = 6 + 20 × P`; retain the meaning rather than treating the exact pixels as
  product logic. Skips remain quiet; social markers use a shared blue treatment and a
  stable size.
- Do not write “no score” for a social event. Label it as a social/cohort plan and
  show the useful context instead.
- A conditional `GO_IF` needs its condition and next action visible in the production
  version, even though the current sample week mostly demonstrates Go, Part, and Skip.
- Week selection changes the displayed map, inventory, and selection together. Avoid
  overemphasizing a fixed weekly capacity number.

The map may remain schematic at first. If it becomes geographic, coordinates must be
traceable to the event location and an unknown location must not be silently placed.

### 3. Event detail

The detail view is a decision explanation, not just a card. It needs:

- the decision and P prominently for a professional event;
- an explicit intent control (Want / Pass in the prototype);
- practical context inputs such as ride, companion, and warm hook, which can trigger
  a recomputation or revised evidence state;
- score factors/evidence at a readable level;
- address, host, RSVP/data state, source provenance, and a direct external event
  listing link;
- an appropriate social treatment without forcing a professional score.

The source link must lead to the actual event website/listing, not merely a generic
host home page whenever a listing URL is known.

### 4. Prep (`#/prep`)

Prep is for an event the person already intends to attend. The page begins with a
specific event selector and then gives an at-a-glance brief:

- host background/context;
- speakers or people to notice;
- one plausible opening question or topic to think about before arriving;
- a direct link back to the event listing.

V12 deliberately labels unencoded research as pending. Retain that distinction: do
not fabricate host bios, speaker bios, attendee lists, or claims about an event.
Suggested data boundary:

```text
event_preparation
  event_id
  research_status             # pending | sourced | reviewed
  source_snapshots[]          # URL, title, fetched/verified timestamp
  hosts[]                     # name, role/context, source reference
  speakers[]                  # name, role/context, source reference
  talking_points[]            # prompt, rationale, status
```

The static `prepBriefs` object in the prototype is illustrative. Replace it with
encoded, cited data rather than treating it as a canonical research record.

### 5. Score a link / intake (`#/intake`)

Pasting a URL creates an `UNSCORED` candidate while preserving the URL and source
label. It must not imply that scoring has finished or manufacture missing event facts.
The candidate should be openable for review once created.

### 6. Read-back (`#/readback`)

When several attended events require a read-back, the user must choose the event first.
The selected event's full title, date, and outcome state remain visible while entering
notes, and every note is stored against that `event_id`.

Keep two visual/data lanes:

- **Recorded**: observed facts that can be corrected immediately.
- **Suspected**: interpretations or hypotheses. Promote only when the project rules
  say evidence is sufficient (the v12 copy uses support at three or more events).

Free text is capture input. Do not turn it directly into a recorded fact without a
reviewable step.

### 7. Learning (`#/learn`)

Learning is an honest calibration view, not a performance report. Retain at least the
v10/v12 material:

- the usable pre-event sample size and its limitation;
- recurring-contact, convening-power, doing-vs-listening, unmodeled-SF-upside, and
  host-prestige hypotheses;
- support/evidence status for each hypothesis;
- felt-versus-delivered examples;
- the frozen standards and coverage disclosure.

Do not overstate conclusions from the current small sample.

### 8. Why this matters (`#/about`)

This page is intentionally one readable editorial flow, not a dense dashboard or a
set of competing columns. It must retain all of these sections:

1. Permission to say no.
2. A plain-language definition of P.
3. The big factors that influence P, without showing a formula: ability to participate,
   who is in the room, a warm way in, and practical friction.
4. A transparent v0 decision explanation.
5. The read-back learning loop.
6. An honest coverage/disclosure section.
7. Frozen standards.

P's formula belongs in inspectable event details or technical documentation, not in
the explanatory editorial flow. The reader should understand the factors before they
need the math.

## Data contract visible to the UI

Use the existing staged pipeline and data ownership described by the project docs.
For each event exposed in this frontend, the UI needs a deliberate representation of:

```text
id, title, starts_at, week
kind / track                    # professional, social/cohort, etc.
location_name, address, location_status
host and host_status
listing_url, source_name, source_url, provenance/verification state
professional decision/outcome   # only when applicable
P and score inputs/evidence     # only when applicable
decision line and, for GO_IF, condition + next action
attendance/registration state
readback records keyed by event_id
```

`data/events.json` remains a bare event array; score aggregates belong in
`data/score_summary.json`. Keep ingestion, enrichment, scoring, and capture separate.
Where a fact is absent, render an honest pending/unknown state rather than an invented
placeholder.

## Visual system to carry forward

V12 is a deliberately different direction from v10:

- dark, spatial field-board background with an information-rich but calm map;
- warm off-white type, bright coral for professional Go/Part emphasis, cobalt blue for
  social/cohort plans, restrained gray for skips;
- large, readable event inventory type (about 17px desktop titles; do not shrink it
  back into dashboard microcopy);
- one strong selected-event panel instead of many equal-weight widgets;
- compact monospaced labels for provenance/status and clean sans-serif reading text;
- a single-column editorial reading width on the explanatory page;
- responsive behavior that stacks the map, selected-event panel, and inventory without
  losing selection or source links.

Use the prototype's CSS and markup as a visual reference, but build semantic,
accessible components: keyboard-selectable map/list equivalents, visible focus states,
proper external-link affordances, and contrast that survives the dark surface.

## Prototype-only material to replace

The following are static design fixtures in `design_v12.html`, not live records:

- `events`, map coordinates, week lists, and score values;
- `prepBriefs` and its deliberately pending research descriptions;
- read-back records and learning summaries;
- the intake-created candidate held only in browser memory.

The frontend should derive these from the actual pipeline/data store and preserve
provenance at every conversion. Do not copy a prototype sentence into production as a
fact unless the source data supports it.

## Build acceptance checklist

- [ ] A week view includes every professional, skipped, and social/cohort event.
- [ ] Every event's decision sentence is readable directly in its list row; a click is
      never required to learn why it was set aside.
- [ ] The default entry state distinguishes current actions from settled skips and
      social/cohort plans, and routes to the relevant focused workflow.
- [ ] Map and inventory stay synchronized; P drives professional bubble size.
- [ ] Selected-event panel shows name, location/address, decision line, score where
      applicable, and the original event listing link.
- [ ] Social plans do not receive a fake P or a “no score” label.
- [ ] Event details expose score explanation, provenance, and conditional actions.
- [ ] Link intake preserves a URL as an unscored candidate.
- [ ] Read-back selects the exact event before capture and separates facts from
      hypotheses.
- [ ] Prep only presents sourced research as fact and visibly marks pending research.
- [ ] Learning includes the v10 evidence/caveat material, not a generic analytics view.
- [ ] Why this matters remains a readable, complete editorial flow and explains P's
      factors without a formula.
- [ ] `scripts/check.sh` passes before handoff.
