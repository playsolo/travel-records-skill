# User-selected recognition profiles

Use this profile when the user explicitly selects it. It is a user/product acceptance rule, not a claim that a reservation proves physical presence. Do not impose it on users who request documentary-only completed stays.

Maintain two dimensions:

- Source evidence: reservation / room ready / post-stay statement / lodging bill; v1 `status` retains reserved/completed/cancelled semantics.
- Recognition: `accepted`, `not_accepted`, or `needs_review`, with reason and related record IDs in a separate review file. An accepted reservation can count under the selected policy while remaining reservation-backed; do not relabel it bill-confirmed. Display distinct evidence labels such as “预订确认” and “账单确认”.

## Retain same-hotel orders; bills determine actual dates

Use `bill_priority_retain_same_property_orders` when the user chooses these rules:

- Same-hotel orders, including two orders for the same dates or multiple rooms, are compatible. Preserve each order and its evidence. A difference in confirmation number, missing booking-order timestamp or room allocation alone does not invalidate them.
- Adopt a displayed reservation when there is no positive contradictory evidence. Unknown fields remain unknown; an incomplete date range prevents counting nights, rather than rejecting the existence of the reservation. Missing or unscoped evidence does not block unrelated orders. Keep an explicitly different traveler separate; adopted booking ownership is not proof of the occupant's identity.
- Within an explicitly linked stay (`stay_key`), a bill's actual dates take priority over the planned range, while the original source range remains unchanged. Independent same-hotel orders are not silently linked or shortened merely because they overlap.
- Compare different properties only when the same traveler scope and actual overlapping dates are known. A bill-supported stay wins over a competing reservation. For conflicting reservation-only orders at different hotels, the user's earlier choice of later **original booking** still applies; reminder/forward/import time is not original booking time. Explicit cancellation remains contrary evidence.
- Count occupancy dates as `[check_in, check_out)`. Take their union per property and traveler scope. Two rooms for May 1–3 contribute **two stay nights**, not four. Also return a date union per traveler scope; order rows are not a count of distinct stays. Never expand a partial date into an invented full range.
- Amounts from independent, non-overlapping financial documents/components may add within the same currency. A bill and its payment/zero balance, a forwarded copy, or a tax invoice for the same spend do not add again. Preserve whether each amount comes from a quote or a bill; apply the selected spending-recognition profile below. Keep financial identity and provenance when aggregating; room count never multiplies a bill total or the stay-night count.

Supply a corroborated `property_key` for same-hotel compatibility; do not infer it by fuzzy title similarity. `room_count` is not used as a stay-night multiplier. The helper returns recognition and unique-night counts, never app writes or monetary aggregation:

```json
{
  "policy": "bill_priority_retain_same_property_orders",
  "stays": [
    {"id": "order-a", "property_key": "hotel-a", "traveler_scope": "account-owner", "evidence_kind": "reservation", "start": "2015-05-01", "end": "2015-05-03"},
    {"id": "order-b", "property_key": "hotel-a", "traveler_scope": "account-owner", "evidence_kind": "reservation", "start": "2015-05-01", "end": "2015-05-03", "room_count": 2}
  ]
}
```

Recognized reservations retain `reserved` status and do not receive a completed-stay badge. Recognition is revisable when new contradictory evidence is actually found; unread or incomplete material alone is not evidence of a conflict.

## Earlier strict profile

Keep `nonconflicting_reservations_latest_booking_wins` for users who explicitly select the earlier stricter behavior. Its rules, after consolidating copies of the same reservation/stay and confirming traveler scope:

1. Retain bill/post-stay-supported actual stays. A reservation overlapping such a stay is not accepted. A newer reservation never overrides stronger actual-stay evidence.
2. Accept an otherwise non-conflicting reservation without requiring photos or another supporting document.
3. If reservation-only candidates overlap, the later original booking wins. The older booking is not accepted as a whole, with a pointer to the newer one; do not trim it into invented partial stays. If that newer booking is itself superseded, do not silently reinstate the older canceled plan.
4. Compare occupancy nights as `[check_in, check_out)`. A checkout on the same date as the next check-in is not a conflict. Compare only the same confirmed traveler scope; explicit multi-room/other-traveler bookings require separate scopes or user review.
5. “Later” means the original booking creation/order time. Do not use a forwarding time, import time, later receipt, later survey or later check-in date. Prefer a booking's stated creation time, otherwise a trustworthy original confirmation sent time. Missing/equal ordering times cannot be arbitrarily tie-broken.
6. Explicit cancellations remain not accepted. Conflicting actual-stay evidence, unknown traveler relationships or incomplete overlap boundaries remain visible for review. A partially dated stay is retained; do not invent its end date to run the conflict algorithm. Unknown dates or traveler scopes must not be treated as proof of no conflict: any reservation that could overlap an unresolved candidate is also held for review, linked to that candidate. Explicit known bounds can rule out overlap; an unknown bound remains open until source reconciliation resolves it.
7. Append decisions and provenance. Never delete source records, user annotations, photos or old dates. A source history record marked not accepted is not a Gmail deletion or an app mutation.

The deterministic helper handles fully dated overnight candidates and emits recognition decisions only:

```json
{
  "policy": "nonconflicting_reservations_latest_booking_wins",
  "stays": [
    {"id": "older", "traveler_scope": "person-a", "evidence_kind": "reservation", "start": "2015-04-25", "end": "2015-04-26", "booked_at": "2015-04-01T12:00:00Z"},
    {"id": "newer", "traveler_scope": "person-a", "evidence_kind": "reservation", "start": "2015-04-25", "end": "2015-04-26", "booked_at": "2015-04-02T12:00:00Z"}
  ]
}
```

```bash
python3 scripts/resolve_stays.py candidates.json > acceptance.review.json
```

Use `stay_evidence` for bill/post-stay-supported candidates, `reservation` for reservation-only candidates, and `cancelled: true` for an explicitly canceled current version. Validate and reconcile versions upstream. Unknown source timing or incomplete stay dates must not be silently filled by the helper. Its output does not write badges, alter v1 fields, or prove extraction accuracy.

### Optional account-order scope

When the user explicitly chooses hotel records from their mailbox without separating occupants, retain those hotel orders without using guest names or payment cards as acceptance gates. Preserve independent orders, deduplicate their evidence and count the union of stay dates. User-facing review needs the property, dates, total amount and evidence type; do not require a tax breakdown, card details or occupant allocation. Unknown totals/dates remain unknown. This preference does not itself change flight-passenger scope or turn prepaid bookings into completed stays.

### Optional missing-year completion

When the user approves completing hotel month/day dates from the original email year, use that year only for the missing year component and record `year_source=original_email_date` in separate review metadata. Clearly label the inferred year in date evidence. Explicit stay years take priority. Use the original provider message, not a later forward/reminder/import timestamp; hold contradictory or year-crossing cases for reconciliation. A message with no stay month/day still has unknown dates. This is a user-selected assumption, not an explicit date quoted from a bill.

An explicitly selected mailbox flight itinerary can be preserved as a reserved mailbox record when personal-traveler allocation is outside the requested scope. Label that scope separately in the review; do not describe it as a verified personal flight or actual boarding. This does not change an existing request restricted to the user's own flights.

### Optional booking-price spending recognition

When the user accepts a booking quote as the consumption price unless contrary evidence is found, use `adopt_booking_price_without_contrary_evidence_bill_first`. For an adopted, non-canceled booking, recognize its quoted price without requiring a payment receipt. Preserve `basis=adopted_booking_quote` in the separate review metadata; this does not change reserved/completed status or assert that payment occurred.

- A stronger amount for the same consumption replaces the quote; do not add quote, bill, deposit and settlement together. Keep historical prices and source links. Preserve independently identified orders even if their dates and prices match.
- Deduplicate repeated representations within one order, not equal amounts across different orders. A combined confirmation can contain two independent room orders plus a grand total: add each order once, never add the grand total again.
- A confirmed whole-order prepaid price can be recognized once. Arbitrary card payments, balances and deposits are not automatically whole-order prices.
- If only a per-room nightly price is provided, calculate a derived recognized price only from explicit dates and room quantity belonging to that quote. Retain rate, nights and rooms as the derivation. A room increase in a separate folio does not automatically multiply an earlier quote.
- Exclude canceled/not-adopted bookings, unbooked optional services, penalties and promotional/menu prices. A card authorization or no-show penalty is not a meal price. Missing price, currency or quantity remains unknown; missing evidence alone is not a contradiction.

Return recognized spending separately from the original financial evidence ledger. Do not relabel an adopted quote as `bill_total` or `payment_entry` to fit that ledger's schema, or add fields unsupported by the app's v1 travel-import schema.
