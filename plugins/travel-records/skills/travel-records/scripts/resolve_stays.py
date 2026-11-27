#!/usr/bin/env python3
"""Apply an explicitly selected stay-acceptance policy; never edits source records."""
import datetime
import json
from pathlib import Path
import sys

POLICY = "nonconflicting_reservations_latest_booking_wins"
RETAIN_ORDERS_POLICY = "bill_priority_retain_same_property_orders"


def day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("full stay dates required")
    return datetime.date.fromisoformat(value)


def instant(value):
    if value is None:
        return None
    result = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("booking timestamp requires timezone")
    return result


def resolve(data):
    if data.get("policy") == RETAIN_ORDERS_POLICY:
        return resolve_retained_orders(data)
    if data.get("policy") != POLICY:
        raise ValueError("acceptance policy must be explicitly selected")
    rows = data.get("stays")
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError("stays must be a list with at most 5000 candidates")
    by_id, dates, clocks, scopes = {}, {}, {}, {}
    results = {}
    for row in rows:
        key = row.get("id")
        if not isinstance(key, str) or not key.strip() or key in by_id:
            raise ValueError("stay IDs must be nonempty and unique")
        if row.get("evidence_kind") not in {"stay_evidence", "reservation"}:
            raise ValueError("invalid evidence kind")
        by_id[key] = row
        scopes[key] = row["traveler_scope"].strip() if isinstance(row.get("traveler_scope"), str) and row["traveler_scope"].strip() else None
        if row.get("cancelled") is not None and type(row["cancelled"]) is not bool:
            raise ValueError("invalid cancellation flag")
        result = {"id": key, "acceptance": "accepted", "reason": "stay_evidence" if row["evidence_kind"] == "stay_evidence" else "nonconflicting_reservation", "related_ids": []}
        if row.get("cancelled"):
            result.update(acceptance="not_accepted", reason="explicitly_cancelled")
        elif scopes[key] is None:
            result.update(acceptance="needs_review", reason="unknown_traveler_scope")
        else:
            try:
                start, end = day(row.get("start")), day(row.get("end"))
                if end <= start:
                    raise ValueError("invalid overnight stay interval")
                dates[key] = (start, end)
            except (TypeError, ValueError):
                result.update(acceptance="needs_review", reason="stay_dates_incomplete_or_invalid")
        # An invalid/missing original timestamp prevents overlap tie-breaking, not accepting an isolated booking.
        try:
            clocks[key] = instant(row.get("booked_at"))
        except (AttributeError, TypeError, ValueError):
            clocks[key] = None
        results[key] = result

    def overlaps(a, b):
        return scopes[a] == scopes[b] and max(dates[a][0], dates[b][0]) < min(dates[a][1], dates[b][1])

    active = [key for key in by_id if results[key]["acceptance"] == "accepted"]
    evidence = [key for key in active if by_id[key]["evidence_kind"] == "stay_evidence"]
    bookings = [key for key in active if by_id[key]["evidence_kind"] == "reservation"]
    for i, a in enumerate(evidence):
        conflicts = [b for b in evidence if b != a and overlaps(a, b)]
        if conflicts:
            results[a].update(acceptance="needs_review", reason="conflicting_stay_evidence", related_ids=sorted(conflicts))
    for a in bookings:
        anchors = [b for b in evidence if overlaps(a, b)]
        if anchors:
            results[a].update(acceptance="not_accepted", reason="conflicts_with_stay_evidence", related_ids=sorted(anchors))
    uncertain = [key for key in by_id if results[key]["reason"] in {"unknown_traveler_scope", "stay_dates_incomplete_or_invalid"}]

    def may_overlap(a, b):
        scope_a, scope_b = scopes[a], scopes[b]
        if scope_a and scope_b and scope_a != scope_b:
            return False
        bounds = []
        for field in ["start", "end"]:
            try:
                bounds.append(day(by_id[b].get(field)))
            except (TypeError, ValueError):
                bounds.append(None)
        lower, upper = bounds
        if lower and upper and upper <= lower:
            lower = upper = None
        start, end = dates[a]
        return not ((upper is not None and upper <= start) or (lower is not None and lower >= end))

    for a in bookings:
        if results[a]["acceptance"] != "accepted":
            continue
        pending = [b for b in uncertain if may_overlap(a, b)]
        if pending:
            results[a].update(acceptance="needs_review", reason="potential_conflict_with_unresolved_record", related_ids=sorted(pending))
    bookings = [key for key in bookings if results[key]["acceptance"] == "accepted"]
    # The user's policy supersedes an older booking if any later booking overlaps it.
    # Do not silently reinstate it if the superseding booking itself is later superseded.
    for a in bookings:
        peers = [b for b in bookings if b != a and overlaps(a, b)]
        later = [b for b in peers if clocks[a] is not None and clocks[b] is not None and clocks[b] > clocks[a]]
        ambiguous = [b for b in peers if clocks[a] is None or clocks[b] is None or clocks[a] == clocks[b]]
        if later:
            results[a].update(acceptance="not_accepted", reason="superseded_by_later_booking", related_ids=sorted(later))
        elif ambiguous:
            results[a].update(acceptance="needs_review", reason="booking_order_unknown_or_tied", related_ids=sorted(ambiguous))
    return {"format": "fotonest.acceptance.review", "version": 1, "policy": POLICY,
            "decisions": list(results.values()), "source_records_deleted": False,
            "note": "Recognition is separate from document status and completion evidence; app not modified."}


def resolve_retained_orders(data):
    """Recognize orders unless positively conflicting; count unique stay dates."""
    rows = data.get("stays")
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError("stays must be a list with at most 5000 candidates")
    records, dates, scopes, properties, clocks, results = {}, {}, {}, {}, {}, {}
    for row in rows:
        key = row.get("id")
        if not isinstance(key, str) or not key.strip() or key in records:
            raise ValueError("stay IDs must be nonempty and unique")
        if row.get("evidence_kind") not in {"stay_evidence", "reservation"}:
            raise ValueError("invalid evidence kind")
        if row.get("cancelled") is not None and type(row["cancelled"]) is not bool:
            raise ValueError("invalid cancellation flag")
        for field in ["property_key", "stay_key"]:
            if row.get(field) is not None and (not isinstance(row[field], str) or not row[field].strip()):
                raise ValueError("invalid " + field)
        records[key] = row
        scopes[key] = row["traveler_scope"].strip() if isinstance(row.get("traveler_scope"), str) and row["traveler_scope"].strip() else None
        properties[key] = row["property_key"].strip() if row.get("property_key") else None
        invalid_dates = False
        try:
            start, end = day(row.get("start")), day(row.get("end"))
            if end <= start:
                raise ValueError("invalid overnight interval")
            dates[key] = (start, end)
        except (TypeError, ValueError):
            invalid_dates = all(isinstance(row.get(f), str) and len(row[f]) == 10 for f in ["start", "end"])
        try:
            clocks[key] = instant(row.get("booked_at"))
        except (AttributeError, TypeError, ValueError):
            clocks[key] = None
        results[key] = dict(id=key, acceptance="not_accepted" if row.get("cancelled") else "accepted",
                            reason="explicitly_cancelled" if row.get("cancelled") else "recognized_without_conflict_evidence",
                            related_ids=[], missing_fields=[])
        if invalid_dates and not row.get("cancelled"):
            results[key].update(acceptance="needs_review", reason="invalid_stay_dates")
        if key not in dates:
            results[key]["missing_fields"].append("complete_stay_dates")
        if not scopes[key]:
            results[key]["missing_fields"].append("traveler_scope")
        if not properties[key]:
            results[key]["missing_fields"].append("property_key")

    def overlaps(a, b):
        return a in dates and b in dates and max(dates[a][0], dates[b][0]) < min(dates[a][1], dates[b][1])

    def competing(a, b):
        return (scopes[a] is not None and scopes[a] == scopes[b] and
                properties[a] is not None and properties[b] is not None and
                properties[a] != properties[b] and overlaps(a, b))

    active = [k for k in records if results[k]["acceptance"] == "accepted"]
    evidence = [k for k in active if records[k]["evidence_kind"] == "stay_evidence"]
    bookings = [k for k in active if records[k]["evidence_kind"] == "reservation"]
    # Reconcile linked planned dates before checking competing hotels.
    # Original input records are retained unchanged.
    for a in bookings:
        stay_key = records[a].get("stay_key")
        if not stay_key:
            continue
        anchors = [b for b in evidence if records[b].get("stay_key") == stay_key and
                   properties[a] is not None and properties[a] == properties[b] and scopes[a] == scopes[b]]
        if not anchors:
            continue
        supported = {dates[b] for b in anchors if b in dates}
        results[a]["related_ids"] = sorted(anchors)
        if len(supported) == 1 and all(b in dates for b in anchors):
            dates[a] = next(iter(supported))
            start, end = dates[a]
            results[a].update(effective_dates=dict(start=start.isoformat(), end=end.isoformat()),
                              date_basis="linked_bill", reason="bill_dates_used_for_linked_reservation")
        else:
            dates.pop(a, None)
            results[a]["missing_fields"].append("unambiguous_linked_bill_dates")
    for a in evidence:
        related = [b for b in evidence if b != a and competing(a, b)]
        if related:
            results[a].update(acceptance="needs_review", reason="conflicting_stay_evidence", related_ids=related)
    for a in bookings:
        anchors = [b for b in evidence if competing(a, b)]
        if anchors:
            results[a].update(acceptance="not_accepted", reason="conflicts_with_stay_evidence", related_ids=anchors)
    bookings = [k for k in bookings if results[k]["acceptance"] == "accepted"]
    for a in bookings:
        peers = [b for b in bookings if b != a and competing(a, b)]
        later = [b for b in peers if clocks[a] is not None and clocks[b] is not None and clocks[b] > clocks[a]]
        unknown_order = [b for b in peers if clocks[a] is None or clocks[b] is None or clocks[a] == clocks[b]]
        if later:
            results[a].update(acceptance="not_accepted", reason="superseded_by_later_booking", related_ids=later)
        elif unknown_order:
            results[a].update(acceptance="needs_review", reason="booking_order_unknown_or_tied", related_ids=unknown_order)

    # Independent orders keep their dates; room count never multiplies nights.
    per_property, per_scope, pending = {}, {}, []
    for key in active:
        if results[key]["acceptance"] != "accepted":
            continue
        if key not in dates:
            pending.append(key)
            continue
        scope = scopes[key]
        # Missing property identity is not evidence that two hotels are the same.
        place = properties[key] or "unresolved:" + key
        per_property.setdefault((scope, place), []).append(dates[key])
        per_scope.setdefault(scope, []).append(dates[key])

    def unique_nights(intervals):
        total, lower, upper = 0, None, None
        for start, end in sorted(intervals):
            if upper is None or start > upper:
                if upper is not None:
                    total += (upper - lower).days
                lower, upper = start, end
            else:
                upper = max(upper, end)
        return total + ((upper - lower).days if upper is not None else 0)
    return dict(format="fotonest.acceptance.review", version=1, policy=RETAIN_ORDERS_POLICY,
                decisions=list(results.values()), source_records_deleted=False,
                nights=dict(method="union_of_accepted_occupancy_dates_excluding_checkout",
                            by_property=[dict(traveler_scope=s, property_key=p, nights=unique_nights(ds)) for (s, p), ds in per_property.items()],
                            by_traveler_scope=[dict(traveler_scope=s, nights=unique_nights(ds)) for s, ds in per_scope.items()],
                            pending_date_record_ids=pending),
                note="Order rows and source status are retained. Room count does not multiply stay nights. Money is reconciled separately; app not modified.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: resolve_stays.py candidates.json")
    try:
        path = Path(sys.argv[1])
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("input exceeds 10 MiB")
        result = resolve(json.loads(path.read_text(encoding="utf-8")))
    except Exception as error:
        raise SystemExit("INVALID STAY INPUT: " + type(error).__name__)
    print(json.dumps(result, ensure_ascii=False, indent=2))
