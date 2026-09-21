# Build handoff — Event Filter

Written 2026-09-18 at the end of the design/grilling phase, for a fresh session to build against.
**Everything needed to start is in this folder. Do not ask the user to re-explain the design.**

Read in this order: `SPEC.md` (authoritative, locked) → this file → `LESSONS.md` (append only,
never rewrite; it is her personal learning blog and the voice is hers).

---

## What this is

A tool that pulls Bay Area AI/tech events from Luma + Haas CampusGroups + Partiful, scores them
for one specific person, explains why, generates prep, and learns from logged outcomes.

The real job is **permission to say no** — not filtering. She is not trying to find more events.
She is trying to skip most of them without anxiety, on defensible grounds.

**The design is settled. Do not re-litigate `SPEC.md`.** It was grilled decision-by-decision and
locked; §6 lists what was resolved and why. If something in it seems wrong, say so explicitly
rather than quietly designing around it.

---

## Who it's for

Ashling Sui. Haas MBA class of 2028 (MBA1, in fall recruiting now). Previously Meituan product
strategy and Deloitte consulting, both Shanghai. Targeting **Big Tech PM / big-startup AI PM**.
**Needs visa sponsorship** — filters most seed-stage startups as employers, but not as sources of
build inspiration.

Hard constraints:
- Lives in Berkeley, **does not drive.** BART reachability is a hard filter. Palo Alto, Menlo
  Park, Marina, Presidio are effectively unreachable. Rides from friends change this — see
  `trip_chained`.
- **No class Fridays.** Friday events cost almost nothing.
- Current bottleneck: her **own website and projects** (portfolio proof-of-work). Resume is done,
  applications are out.

Working preferences, learned the hard way:
- She corrects over-abstraction, and her corrections have been right every time. Take them.
- **Never frame going to events with friends as a cost.** Companions are a positive: less nervous,
  more likely to attend, and the debrief afterward extracts more value. The thing that kills
  new-contact yield is `cohort_saturation` (a room of people she already knows), not company.
- She likes sharp one-line reframes that recast her own data. Lead with those, not balanced lists.

---

## Verified technical findings — do not rediscover these

All checked live on 2026-09-17/18.

**Luma — per-calendar ICS, no RSVP and no calendar subscription required:**
```
https://api.lu.ma/ics/get?entity=calendar&id=cal-XXXXXXXX
```

**Luma — richer JSON (undocumented internal endpoint; enrichment only, may break):**
```
https://api.lu.ma/calendar/get-items?calendar_api_id=cal-XXXXXXXX&period=future&pagination_limit=50
```
Returns `geo_address_info` (city, address, lat/lng) — this is what BART scoring needs.

**Luma event pages** parse via the `<script id="__NEXT_DATA__">` JSON blob:
`props.pageProps.initialData.data` → `event` (name, start_at, end_at, geo_address_info),
`hosts[]`, `guest_count`, `calendar` (name + api_id).

**`lu.ma/sf`** exposes ~19 calendar ids in the same blob — scriptable calendar discovery.

**Haas CampusGroups — JSON, no auth:**
```
https://haas.campusgroups.com/mobile_ws/v17/mobile_events_list?range=0&limit=50
```
Returns the full Haas feed regardless of `group_ids`, so pull everything and filter locally.
Fields arrive as positional `p0..pN` keys: name, HTML date string, category
(Academic/Social/Ticket Sales), venue, group id. **Group id is how Tech Club and PM Club route to
the career stream and Wine Club routes to cohort.**

**Partiful** (Tech Week events live here): no API found; `og:title` / `og:description` meta tags
parse fine. Separate ingest.

**Coverage is not complete and the UI must not imply it is.** Luma has no global search; recall is
exactly the union of followed calendars.

---

## Starting calendar list

Participant-side (build/product — her profile):
| Calendar | id |
|---|---|
| OpenRouter Events | `cal-cv816PW6bxfYMVP` |
| Claude Community Events | `cal-TOpA5LAFfuDeFpu` |
| Claude Workshops | `cal-8ACK0vjqOfKpHXl` |
| Codex SF | `cal-PKTAt8IpN9ZHTFK` |
| South Park Commons | `cal-Ve0M7LoDOpdnF3z` |
| Stripe Developer Meetups | `cal-8EtFfS1gDogglBc` |

Spectator-side, keep but down-weight: Berkeley SkyDeck Fund `cal-0WfGKFnaMuZk0Oj`,
Afore Events `cal-jG6uA6fcSEneQJB`.

Drop as noise: Bakar Labs, Read in the Park, Spatial Frontier, MCBcDNA, 7PACIFIC, NODE (Palo Alto).

Still needed from her: Haas Tech Club and PM Club — confirm whether they post on Luma or only
CampusGroups (her Fintech Club event was on Luma, so both may be in play).

---

## Labeled data so far

| Event | Date | Outcome |
|---|---|---|
| a16z Grok Bot build night for women (SF, a16z office, small) | 2026-09-03 | **HIT** — adopted Grok Bot day one (S3), met Zara Zhang (S2). Value was the *demos*, per her. |
| Haas Founder & Funder Night (Berkeley SkyDeck, 200) | 2026-08-19 | **NULL** — felt "amazing," delivered nothing. Wrong ladder + high cohort saturation. |
| Venture Math S02 (campus, 73) | 2026-09-09 | **NULL** — spectator, off-target topic. |

**Granola notes exist for the Grok Bot event** and she offered them. Worth ingesting — and worth
running the decay test on: how much of what she wrote down two weeks ago has she actually used?

## Predictions locked before the fact — DO NOT EDIT THESE

`predicted_p` = P(S2 contact OR S3 build). Recorded 2026-09-18, pre-event.

| Event | When | predicted_p | Reasoning |
|---|---|---|---|
| OpenRouter × a16z, "New Model Dilemma" | Fri 2026-09-18, 12–2pm, SF | **0.60** | Participant, real prior hook (uses the product), zero cohort saturation, top-tier host. Cost ≈ 0 (Friday, Ivy driving, on the way to Yosemite). Lowered by the hard stop — leaving for Yosemite kills the post-event mingle where contacts form. |
| Swift Ventures founders' fireside | Thu 2026-09-24, Berkeley, 49 | **0.30** | Spectator format, `wrong_ladder` for S2 (VC, not a target employer), fireside rarely produces builds. Rescued somewhat by `prior_hook = person` — she's met him. Cheap, so still plausibly worth going. |
| AI Heist (Cogent × Modal × LangChain) | SF Tech Week, TBD | **0.70** | Best profile in the set: team-based build format forces interaction, `participant = true`, Modal/LangChain people are on-target, zero cohort saturation. |
| Love at First Slide (Gamma × Atlassian) | SF Tech Week, TBD | **0.55** | She would be *presenting* — memorability inverts networking. Atlassian is a scaled sponsor-capable employer. She has unusually strong material (BaZi, art advisory). |

Her felt-score and T+7 labels for these are the first real calibration rows. **Collect them even if
the tool isn't finished** — outcomes accrue on calendar time, not build time.

---

## Build sequence

1. **Ingest** — Luma ICS + campusgroups JSON + partiful → normalized rows against the `SPEC.md` §2
   schema. Config-driven calendar list.
2. **Enrich** — LLM pass fills `participant`, `target_proximity`, `format`, `cohort_saturation`,
   `prior_hook`. Geocode → `bart_walk_min` → `reachable`.
3. **Score** — hard filters first, then weighted combination minus `cost_blocks`. Output
   `predicted_p` and go / skip / **go-for-part-only** (partial attendance is first-class).

   **The verdict leads; the score is secondary.** She reported at the end of the design session
   that her FOMO had not moved at all — because reasoning produces *reasons* to skip, and a reason
   is something you negotiate with at 11pm on a Luma page. The UI must state a decision out loud,
   with the reason attached underneath. A ranked list leaves the decision open, and an open
   decision is what the anxiety feeds on. Never ship a bare ranking.

   ### Step 3 output contract (added 2026-09-18)

   Cheap and non-frozen — this is output format, not a label change.

   Per scored event:
   ```
   verdict          go | part | wildcard | skip | blocked
   primary_reason   one code — the one the UI displays
   reasons[]        all applicable codes
   ```

   Fixed reason-code set (don't invent new ones silently):
   ```
   not_reachable    hard filter — no BART and no ride
   conflict         overlaps something already committed
   quota_full       would otherwise be a GO, but the week's slots are taken
   spectator        participant = false
   wrong_ladder     target_proximity = wrong_ladder
   recurring        next occurrence within ~3 weeks
   off_phase        wrong phase (build vs interview)
   below_bar        nothing categorically wrong, just didn't score high enough
   ```

   Precedence for `primary_reason`, highest first:
   `not_reachable > conflict > spectator > wrong_ladder > recurring > off_phase > below_bar`

   **Exception:** `quota_full` outranks everything except `not_reachable` and `conflict`, but only
   applies to events that scored **above** the bar. An event that was never going to make it
   should say why it's weak, not blame the quota.

   Also emit aggregates so the UI doesn't recompute them:
   ```
   skip_summary     { total, by_reason: { code: count } }
   blocked_summary  { total, by_reason: { code: count } }
   ```

   Keep blocked separate from skipped — blocked events were never scored, so they must not appear
   in any hit-rate denominator later.

   **Why this exists:** at real volume the page is ~40 events and ~3 GOs. Rendering 37 grey skip
   rows is both bad design and a reintroduction of the problem the tool exists to remove — 37
   enumerated skips is 37 chances to second-guess. Skips collapse into a count
   ("34 skipped — 12 not reachable, 15 spectator, 7 recurring") with a toggle to expand.

   `quota_full` is the most important code in the set: it is the only one meaning *"this was good
   and you still can't go."* That is the most FOMO-sensitive case in the system and it has to say
   so plainly, rather than hiding behind a low score and quietly teaching her that good events
   were bad ones.
4. **Capture** — T+0/T+1 felt score, T+7 three yes/no **recognition-style** (show scraped speaker
   names, never ask her to recall), T+30 batch sweep. Read `contacts.csv` read-only to auto-propose
   S2 labels — **approved by her, read-only, never writes.**

   **Intent capture — see `SPEC.md` §1b, added 2026-09-18.** Her own want/pass judgment on every
   scored event, including ones she never attends. New fields: `intent`, `intent_at`,
   `intent_anchored`, `gated`, `rsvp_state`. It is a *preference* label — it never enters `hit`
   and never touches `predicted_p`. `rsvp_state = rejected` is **not** a pass and must be excluded
   from every skip count and rate denominator. Marking "want" opens a three-field context strip
   (`trip_chained`, `companions`, `prior_hook`) and **recomputes the verdict** — those three
   cannot be scraped and are the leading suspect in the 0.20-vs-0.60 gap on the OpenRouter event.

   **Free text first, structure second. Do not build forms.** The single highest-signal data in
   this project came from her describing past events in her own words — "it was fun, the food and
   drinks were great" vs. "I've been experimenting with it since day one" are completely different
   outcomes that any dropdown would have collapsed into "interesting." Capture the sentence, let
   the model extract the fields. Her own `TRACKER.md` states the same rule: *"Chat is the input.
   Do not build forms."*
5. **Frontend** — **`prototype.html` in this folder is the approved visual target. Build to it; do
   not invent a different look.** It was designed with her and signed off 2026-09-18. Palette is
   BART line colors on near-black, IBM Plex Mono + Plex Sans, and the structure is a **verdict
   stack, not a card grid** — that distinction is load-bearing, see step 3.

   Sections: This Week (verdict + reason + factor chips + locked `predicted_p`) · History ·
   **Calibration** (the panel that makes it a portfolio piece) · Watchlist · Prep. Left icon rail
   carries **state badges** (checks due, briefs ready) — the badges are why the rail exists; a
   nav-only rail is furniture and should be dropped.

   Top status bar shows **only things she would act on** — slots left, next commitment, next RSVP
   closing, outcome checks due. She explicitly rejected system-vanity counters ("scanned 31,
   calendars 8"). Don't put them back.

   **Paste-a-link box is a real feature, not decoration.** Accepts Luma / Partiful / CampusGroups
   URLs and queues them for parsing — it covers the coverage gap (private invites, links forwarded
   by friends, calendars she doesn't follow).

   Static page reading baked-in data, same pattern as her recruiting dashboard, so it opens
   anywhere with no server. **She wants to demo this to people — it should read well cold.**

   *Design sequencing:* the visual direction is locked now, deliberately, so it can't drift. The
   **second** design pass belongs after step 2 (enrich) lands real data at real volume — 40 events
   a week, long titles, `"Private Location (sign in to display)"`, missing hosts. Those failure
   modes don't exist at the 7 hand-picked rows the prototype was designed against. A third pass,
   for portfolio polish, belongs after ~10 labeled events, when the calibration panel finally has
   something in it.
6. **Push alerts** — daily scan, alert only on high scorers, flag RSVP-closing-soon first. Good
   small events gate and fill fast, so latency matters more than filtering at the top.

Don't build 4 and 5 before 1-3 produce real rows.

---

## Open, cheap, decide with data

- `prior_hook` is scored pre-event but is manufacturable by prep — feature, intervention, or both?
  Does prep contaminate the label?
- Phase transitions: who flips `build` → `interview`, on what trigger?
- Alert thresholds / how noisy push may be.
- What the frontend must prove to a recruiter reading it cold.
