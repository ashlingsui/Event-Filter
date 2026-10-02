"""Hand-entered values are authoritative; pipeline stages must not overwrite them.

A row can carry  _manual: {fields: [...], set_by, note}  — the fields a human set by hand because
the pipeline cannot know them (e.g. reachable for a Partiful event with no address). Until this
module existed NOTHING read that key, and re-running a stage silently replaced hand-set
predicted_p, reachable and cost_blocks with computed guesses — each time producing a
plausible-but-wrong board with no error anywhere.

Mechanism: stage-agnostic snapshot / compare / restore around each pipeline step, so it covers
every field a stage might write, including ones added later, without editing each assignment.

    report = manual_guard.Report()
    with report.protect(rows, "enrich:geocode"):
        geocode.enrich_all(rows)
    ...
    report.print_summary()          # never silent: states the count even when it is zero

Whatever a stage WOULD have written is kept in  _manual.shadow[field]  so disagreement between the
hand-set value and the pipeline stays visible (and reviewable) instead of vanishing.
"""
import contextlib
import copy
import datetime as dt


def protected_fields(row):
    manual = row.get("_manual")
    if not manual:
        return []
    fields = manual.get("fields")
    if not isinstance(fields, list):
        raise ValueError(
            "row {!r} has a malformed _manual (fields must be a list, got {!r}) — refusing to "
            "guess which fields are protected".format(row.get("name") or row.get("id"), fields)
        )
    return fields


def _record_shadow(row, field, stage, would_write, kept):
    manual = row["_manual"]
    manual.setdefault("shadow", {})[field] = {
        "stage": stage,
        "would_have_written": would_write,
        "kept": kept,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


class Report:
    def __init__(self):
        self.guarded_rows = 0
        self.checks = 0            # (row, protected field) pairs examined, across all stages
        self.agreed = 0            # stage output equalled the hand-set value
        self.blocked = []          # dicts: stage, row, field, kept, would_have_written

    def _note_rows(self, rows):
        self.guarded_rows = max(self.guarded_rows, sum(1 for r in rows if protected_fields(r)))

    @contextlib.contextmanager
    def protect(self, rows, stage):
        snapshot = []
        for row in rows:
            fields = protected_fields(row)
            if fields:
                snapshot.append((row, {f: copy.deepcopy(row.get(f)) for f in fields}))
        self._note_rows(rows)
        try:
            yield
        finally:
            for row, kept_values in snapshot:
                for field, kept in kept_values.items():
                    self.checks += 1
                    now = row.get(field)
                    if now == kept:
                        self.agreed += 1
                        continue
                    _record_shadow(row, field, stage, copy.deepcopy(now), kept)
                    self.blocked.append({
                        "stage": stage, "row": row.get("name") or row.get("id"), "field": field,
                        "kept": kept, "would_have_written": now,
                    })
                    row[field] = copy.deepcopy(kept)

    def carry_forward(self, existing_row, fresh_row, stage="ingest:merge"):
        """Ingest replaces a live event's row wholesale with the fresh pull. Carry the hand-set
        values (and the _manual record itself) from the old row onto the new one, recording what
        the fresh pull said."""
        fields = protected_fields(existing_row)
        if not fields:
            return fresh_row
        fresh_row["_manual"] = copy.deepcopy(existing_row["_manual"])
        for field in fields:
            kept = copy.deepcopy(existing_row.get(field))
            would = fresh_row.get(field)
            self.checks += 1
            if would == kept:
                self.agreed += 1
            else:
                _record_shadow(fresh_row, field, stage, copy.deepcopy(would), kept)
                self.blocked.append({
                    "stage": stage, "row": fresh_row.get("name") or fresh_row.get("id"),
                    "field": field, "kept": kept, "would_have_written": would,
                })
            fresh_row[field] = kept
        return fresh_row

    def as_dict(self):
        return {
            "rows_with_manual_fields": self.guarded_rows,
            "field_checks": self.checks,
            "preserved_unchanged": self.agreed,
            "overwrites_blocked": len(self.blocked),
            "blocked": self.blocked,
        }

    def print_summary(self, file=None):
        print("\nManual-value preservation (_manual.fields):", file=file)
        print("  {} rows carry hand-set fields; {} (row, field) checks across this run's stages."
              .format(self.guarded_rows, self.checks), file=file)
        print("  {} stage-checks found the hand-set value already matching what the stage "
              "produced; {} overwrite(s) BLOCKED and recorded in _manual.shadow."
              .format(self.agreed, len(self.blocked)), file=file)
        for b in self.blocked:
            print("    BLOCKED [{stage}] {row!r}: {field} kept {kept!r}, stage wanted {would_have_written!r}"
                  .format(**b), file=file)
