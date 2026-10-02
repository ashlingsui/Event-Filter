"""Canonical Event Filter row shape — SPEC.md §2. Frozen fields are never redefined, only added to."""

EVENT_SCHEMA_VERSION = 1

SOURCES = ("luma", "campusgroups", "partiful")


def new_event():
    return {
        # identity
        "schema_version": EVENT_SCHEMA_VERSION,
        "id": None,
        "source": None,
        "url": None,
        "name": None,

        # pre-event — must be knowable before the decision, no leakage
        "start": None,
        "end": None,
        "duration_hr": None,
        "venue": None,
        "city": None,
        "lat": None,
        "lng": None,
        # Region classification at ingest time — see ingest/region.py. "in_region" | "out_of_region"
        # | "unknown". A row reaching data/events.json should never be "out_of_region" (its
        # calendar's filter should have dropped it) — app/build_data.py treats that as a bug
        # signal, not something to quietly re-filter. Distinct from `reachable`, a BART-walk cost
        # computed later in enrich/ — this is "is it even in California," not "can she get there."
        "region_status": None,
        "bart_walk_min": None,
        "reachable": None,
        "host_names": [],
        "host_tier": None,
        "format": None,
        # SPEC.md §3b — one format enum can't describe a mixed agenda ("first 30 minutes hanging
        # out, then an hour of demos"). Top-level `format` remains the dominant segment; this is
        # additive detail, RECORDED-BUT-UNWEIGHTED today (score/scorer.py's S3 still reads
        # top-level `format` only — see that file for why wiring segments into the value formula
        # is a separate, not-yet-built change). [{kind, duration_min, source}], source = described
        # | inferred | rule.
        "segments": [],
        "size": None,

        # speakers — added 2026-09-21, RECORDED-BUT-UNWEIGHTED (SPEC.md §1c "record early, weight
        # late"). Not read anywhere in score/scorer.py. Sharper than host_tier alone: a small
        # company's own event that lands a well-known speaker beats a generic tier1_vc mixer, and
        # only speaker-level data can see that difference. [{name, title, employer, source}]
        "speakers": [],
        "participant": None,
        "target_proximity": None,
        "cohort_saturation": None,
        "prior_hook": None,
        "companions": [],
        "trip_chained": False,
        "cost_blocks": None,
        "recurring": False,
        "next_occurrence": None,
        "phase": None,
        "predicted_p": None,
        # SPEC.md §3c — fraction of score/scorer.py's CONFIDENCE_FIELDS actually known on this
        # row, set by score_row(). Low confidence routes to the `unscored` verdict (score/
        # verdicts.py) instead of a confident go/skip computed from neutral priors.
        "confidence": None,
        "is_exploration": False,

        # intent — SPEC.md §1b, added 2026-09-18. Her own want/pass judgment, captured at
        # decision time. A PREFERENCE label, not an outcome — never enters `hit`, never touches
        # `predicted_p`. Storage/shape only here; the capture UI (the three-tap context strip:
        # trip_chained / companions / prior_hook, opened by marking "want") comes with step 5.
        "intent": "undecided",          # want | pass | undecided
        "intent_at": None,              # timestamp
        "intent_anchored": None,        # bool — was the verdict visible when she marked it?
        "gated": False,                 # bool — RSVP requires approval or has capacity
        "rsvp_state": "none",           # none | applied | waitlisted | confirmed | rejected

        # post-event — filled by the capture step (T+0/T+7/T+30), never by ingest
        "attended": None,
        "partial": None,
        "felt_score": None,
        "felt_note": None,
        "s1_pov": None,
        "s2_contact": None,
        "s3_build": None,
        "s4_cohort": None,
        "hit": None,
        "label_status": "unknown",

        # source-specific context for the enrichment step; not part of the frozen schema
        "_raw": {},
    }
