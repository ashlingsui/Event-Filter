/*
 * people + event_people — PREP_SPEC.md §4's tables, §6 build-order steps 1-2 only: structure and
 * the watchlist feed, populated from speaker names data/events.json already carries. No identity
 * resolution here — every person is identity_status "not_found" until a later, server-side step
 * (PREP_SPEC.md §2/§3, gated on real research infra) resolves who they actually are. Matching is
 * literal, case-insensitive name string equality; it is not identity resolution and must never be
 * presented as one.
 *
 * A pure derivation over DataAccess.getEvents(), rebuilt on every call — nothing here is stored.
 * Everything it needs is already in the committed public snapshot (app/generated/data.js), and
 * there is no write path that would make caching worth the staleness risk. One table serves both
 * the prep screen and any future watchlist view — PREP_SPEC.md §3: "build it once."
 */
const PeopleData = (() => {
  function slugify(name) {
    return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  function speakerName(s) {
    return typeof s === "string" ? s : (s && s.name) || null;
  }

  function build() {
    const people = {};
    const eventPeople = [];

    DataAccess.getEvents().forEach((e) => {
      (e.speakers || []).forEach((raw) => {
        const name = speakerName(raw);
        if (!name) return;
        const id = `unresolved:${slugify(name)}`;
        if (!people[id]) {
          people[id] = {
            id,
            display_name: name,
            identity_status: "not_found", // PREP_SPEC.md §2 — resolution is a separate, gated step
            identity_evidence: [],
            current_role: null,
            current_employer: null,
            recent_public: [],
            connection_to_user: [],
            researched_at: null,
            research_cost_tokens: 0,
          };
        }
        eventPeople.push({
          event_id: e.id,
          person_id: id,
          role: "speaker",
          source_ref: "data/events.json speakers[]",
        });
      });
    });

    return { people, eventPeople };
  }

  function getPeople() {
    return build().people;
  }

  function getEventPeople() {
    return build().eventPeople;
  }

  // Rows for one event, each carrying appearance_count — how many events (including this one)
  // this literal name has been named at. That count is the passive watchlist signal PREP_SPEC.md
  // §3 describes; it is not evidence the same real person is meant, just the same name string.
  function getPeopleForEvent(eventId) {
    const { people, eventPeople } = build();
    const counts = {};
    eventPeople.forEach((ep) => {
      counts[ep.person_id] = (counts[ep.person_id] || 0) + 1;
    });
    return eventPeople
      .filter((ep) => ep.event_id === eventId)
      .map((ep) => ({ ...people[ep.person_id], role: ep.role, source_ref: ep.source_ref, appearance_count: counts[ep.person_id] }));
  }

  // Every distinct name across every scanned event, most-repeated first — "accumulate passively
  // from scanned speaker names," per SPEC.md §5's cold-start note. Not rendered anywhere yet;
  // this is the feed a future watchlist view reads from.
  function getWatchlist() {
    const { people, eventPeople } = build();
    const eventIdsByPerson = {};
    eventPeople.forEach((ep) => {
      (eventIdsByPerson[ep.person_id] || (eventIdsByPerson[ep.person_id] = [])).push(ep.event_id);
    });
    return Object.keys(eventIdsByPerson)
      .map((id) => ({ ...people[id], event_ids: eventIdsByPerson[id] }))
      .sort((a, b) => b.event_ids.length - a.event_ids.length || a.display_name.localeCompare(b.display_name));
  }

  return { getPeople, getEventPeople, getPeopleForEvent, getWatchlist };
})();
