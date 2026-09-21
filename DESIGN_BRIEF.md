# Design brief — Skip or Go

Point a design session at **this file** and nothing else. Everything it needs is here or linked
from here.

---

## What the product is

A personal decision tool. It pulls Bay Area AI/tech events from Luma, Haas CampusGroups and
Partiful, scores them for one person, and tells her **go / skip / go-for-part-only** with the
reasoning attached.

The job is **permission to say no**, not discovery. She is not trying to find more events. She is
trying to skip most of them without anxiety.

Second audience: recruiters. She will show this. It has to read well cold.

---

## The two references, and what each is for

**AWS Builder Center is the primary reference. Partiful is secondary.**

The product's voice, palette discipline, typography and overall feel come from AWS Builder Center.
If the two ever conflict, AWS wins. Partiful is borrowed narrowly — for one screen and one
component — and its playful register is explicitly **not** adopted.

They are not two flavours to blend. They are **two different screens.**

### AWS Builder Center → PRIMARY. Sets the whole visual system.
Near-black ground, monospace headings, flat pixel-art icons in bright accent colors, restrained
layout, lots of dark space, accent used only on icons.

**Take:** the typographic voice, the dark restraint, the icon treatment, the builder-identity feel.
**Do NOT take:** the equal-weight card grid. A grid of identical cards says *"here are options,
pick one"* — which rebuilds the exact open-decision problem this tool exists to remove.

### Partiful → SECONDARY. One screen and one component only.
Near-black with a soft ambient radial glow, centered single column, big bold centered title, one
large rounded image card, friendly oversized date/time, and a full-width rounded CTA pill.

**Take:** the centered single-event treatment, the ambient glow over flat black, the confident
oversized type, and especially the **big chunky CTA pill** — that is exactly the right shape for
*Want to go* / *Pass*.
**Do NOT take:** the playful party voice, or the bottom tab bar.

---

## Already decided — do not undo these

Each of these was argued out with the user. Changing one is a regression, not a fresh idea.

1. **Verdict stack, never a card grid.** Decision on the left, reason attached, probability demoted
   to the right margin. The verdict leads; the score is secondary.
2. **SKIP is calm grey, never red.** Red is reserved for hard blocks only. If skipping looks like
   an alarm state, the interface re-creates the anxiety the tool exists to remove. Skipping should
   look *settled*.
3. **No vanity metrics.** Top-of-page shows only things she would act on — slots left, next
   commitment, next RSVP closing, outcome checks due. She explicitly rejected "scanned 31 /
   calendars 8". Do not put them back.
4. **The left rail exists because it carries state badges** (checks due, briefs ready). A nav-only
   rail is furniture — if the badges go, the rail goes.
5. **Her four principle lines, verbatim.** Wording is hers, not to be improved:
   - *"Is this event for someone like me, or am I watching someone else's event?"* (headline)
   - *"A prior hook is what makes an event warm for you."*
   - *"Scoring picks the room; follow-up is what converts it."*
   - *"Watching people instead of watching events — let me build your watchlist."*
6. **Palette: BART line colors** — green `#00B94F`, yellow `#FFC400`, red `#E4002B`, blue
   `#189FD8`, orange `#F58025` on near-black. Chosen because she doesn't drive and BART
   reachability governs her life; it is the Bay's own signage language.
7. **Type: IBM Plex Mono + IBM Plex Sans.** Open to change, but replace the pair deliberately —
   not with Inter or Space Grotesk.

`prototype.html` in this folder is the approved v1 of the list surface. Build from it.

---

## What's new since the prototype — this is the actual design work

1. **Event detail page.** Does not exist yet. This is where the Partiful language goes: click an
   event → centered page → big *Want to go* / *Pass* pills.
2. **The context strip.** Marking "want" opens three quick inputs — *have a ride? · going with
   someone? · already use this / follow this person?* — and the verdict **recomputes in place.**
   These three can't be scraped and are the single biggest source of model error. Make answering
   them feel like one gesture, not a form.
3. **The read-back panes.** After she describes an event in her own words, the system shows what it
   heard, in **two panes that must never visually merge**:
   - **Recorded** — extracted facts. She corrects them; corrections apply immediately.
   - **Suspected** — inferences. She *cannot* approve these. They accumulate a counter.
   The separation is load-bearing: if an inference sits next to four correct facts, she rubber-
   stamps it. Make them look like different kinds of object, not two columns of the same card.
4. **Pending hypotheses list.** Things the system suspects but hasn't earned the right to act on,
   with a support counter (`2 of 3`). This is the most interesting screen for a recruiter — it is
   visible epistemic honesty. Do not bury it.
5. **`go_if` verdict.** A conditional: *"GO — if you can get a ride."* Needs a visual state of its
   own, distinct from GO and SKIP, and the unblocking condition reads as an **action**.
6. **Suppressed count.** ~60 events/week are suppressed as unreachable. Shown as a single honest
   line, never as 60 rows.
7. **Skip collapse.** Skips collapse into a summary — *"34 skipped — 12 not reachable, 15
   spectator, 7 recurring"* — with a toggle. 37 enumerated skip rows is 37 chances to second-guess.
8. **Free-text feedback input.** She talks, the model extracts. **Never build a form.** Her own
   phrasing is the highest-signal data in the project.

---

## Design against real data, not lorem

- `data/events.json` — ~108 real scored events. Long titles, missing hosts, hidden guest counts,
  `"Private Location (sign in to display)"`. Design for that mess, not for seven tidy rows.
- `data/outcomes.json` — 4 labeled events.
- `data/pending_hypotheses.json` — 5 hypotheses, 2 with support.
- `data/score_summary.json` — verdict counts and reason breakdowns.

---

## Do NOT finish the calibration panel yet

It has **one** usable row. Only the OpenRouter event has a prediction recorded before the fact; the
other three were backfilled and can never contribute to a track record. Design the *container* and
its empty state honestly — *"1 of ~10 rows. Too few for a rate."* — and leave the full treatment
for when there is something in it. Never let the UI imply n=4.

---

## Baseline requirements

Works at ~400px. Keyboard focus is visible. Respects `prefers-reduced-motion`. Single static page
reading baked-in data — no server, opens anywhere, same pattern as her recruiting dashboard, so she
can send someone a file.
