# Extraction and accountable coverage

The input is evidence, not a registry of supported hotels. Use the host AI to interpret new layouts. Deterministic helpers normalize, checkpoint, reconcile and validate; they do not replace semantic extraction. For multi-message or continuing work, use [the executable evidence protocol](evidence-workflow.md) instead of writing a new provider-specific reconciliation script. A one-off supplied screenshot can still be extracted directly to v1 with a separate review.

## 1. Discover and inventory

Verify the selected mailbox identity before searching. Follow account-specific connection arguments on every search/read/attachment call. Search transaction words, localized equivalents, known sender domains and observed staff/property names. Include inline eFolio, post-stay surveys and attachments, not just subjects containing “reservation”. Paginate queries and state their actual scope.

Read the tool's current account choices/connection arguments and verify each selected identity with a cheap profile read before initializing the session. Missing `link_id` is an argument/configuration error; discover the available account binding before diagnosing authorization failure. For annual work, use only the requested mail year(s), including follow-up searches. Do not expand source years to compensate for a trip's missing confirmation or bill; the user may explicitly add years later.

Create an inventory entry for each selected message body and each potentially relevant attachment. Keep source IDs stable and account-scoped. Keep opaque document IDs and content hashes so forwarded or cross-mailbox copies add provenance instead of more visits. Do not put account addresses, connection identifiers or attachment tokens in public fixtures.

For large result sets, use bounded reading batches and save a resumable, account-scoped pending-message queue with the discovery scope, pagination cursors and current dispositions. Resume unresolved messages and attachments on continuation instead of repeating completed searches. State discovered/read/extracted counts separately. Balance a diagnostic sample across accounts, dates and evidence types; processing the first results alone cannot demonstrate coverage of old bills, unfamiliar senders or other categories.

For local `.eml` files or a single connector MIME-tree JSON, use:

```bash
python3 scripts/normalize_email.py input.eml --account mailbox-a --output-dir private/source-a
```

The output is private normalized source material, not the final export. Attachment payloads are stored only when supplied locally; remote attachment references still require the authorized connector. No links are followed. For PDF/image attachments use available text extraction, then OCR and visual inspection if text is damaged or label/value columns become detached. Do not substitute mail timestamps for stay dates. A user-selected missing-year completion profile may supply only a missing hotel year, with provenance; see [stay acceptance](stay-acceptance.md).

For a relevant PDF with an incomplete preview, retrieve the complete extraction or original attachment through the connector while within the reading budget. In Gmail, use the returned complete extraction reference if accessible, otherwise the returned original file reference. Verify the relevant pages and inspect the printed header if the property is a logo or missing from the extracted text. Mark the attachment parsed only after reading the source used for the fields. If retrieval fails, record the actual failure and keep the attachment pending for follow-up.

The selected body is a reading aid. Inspect retained MIME alternatives when the selected text is only browser/opt-out boilerplate or important fields are missing. A longer plain part may consist of tracking URLs. Do not extract dates or personal details from opaque URL parameters as though they were visible transaction fields.

### Schema.org reservation markup

When an HTML MIME body contains a `script` block with type `application/ld+json`, the normalizer adds supported records to the private body's `structured_reservations`. A candidate includes its MIME part, script index, JSON path, reservation type and extracted fields. Read `structured_warnings` when a block is malformed or exceeds a limit. The normalizer retains the visible body and its usual selection rules.

For a standalone JSON-LD file, HTML file or saved attachment, use the same extractor:

```bash
python3 scripts/read_reservation_jsonld.py private/booking.jsonld
```

This reads compact Schema.org `LodgingReservation`, `FlightReservation` and `FoodEstablishmentReservation` with standard field names, including arrays, `@graph` and unambiguous references defined in the same JSON block. Schema.org and Gmail email-markup spellings of the reservation ID and status are accepted. Other JSON-LD vocabularies, custom aliases and remote references are outside this reader's scope. It reads JSON as data, with no script execution or network access. Keep the raw reference and the extractor's output private.

Carry the candidates into the [existing evidence batch](evidence-workflow.md#ai-extraction-batch):

- Check visible dates, endpoints, status and amounts against the markup when both are available. If they disagree, preserve both with their source locations and resolve the discrepancy or leave it for review. A missing field can be read from the body or an authorized attachment. A time-of-day without a date is no evidence for a calendar day.
- A confirmed reservation supports `reserved`, an explicit cancellation supports `cancelled`, and a hold or pending reservation supports `processing`. A reservation node without a recognized state leaves the status unresolved until supported by other evidence. Only separate evidence of completion can support `completed`.
- Preserve source offsets and times in the evidence and review. Use the sender's local calendar days for v1 and keep a range it cannot represent in review. A confirmation number can help link evidence when scoped to the provider and order component. Multiple passengers on the same flight are not extra flight legs.
- Map a clear `totalPrice` to an amount observation with basis `booking_total` only when its transaction scope and currency are supported. Use one financial unit per underlying order when explicit. Booking markup can describe a quoted total, so keep a matching final bill as separate evidence. The standard v1 export still contains the reviewed travel fields.

For messages without usable markup, continue with the existing body and attachment workflow. A markup miss does not rule out a booking. The reader currently covers this JSON-LD subset and does not process Microdata.

## 2. Extract and reconcile

Keep each field's supporting excerpt and document identity. Extract the following when explicit:

| Evidence | Record and interpretation |
| --- | --- |
| Hotel confirmation | Property, guest relation, check-in/out, reserved/cancelled state. Marketing, cancellation policies and cancellation links are not actual events. |
| Lodging folio | Actual arrival/departure, bill currency and separate monetary components. Keep lodging and incidentals tied to the same stay. Printed/issued dates are separate. |
| Inline eFolio | “Dates of stay”, charges, rebates, cash/card/voucher/advance payments and balance. No attachment is required. Zero balance is not zero spend. |
| Post-stay survey | Property and exactly stated beginning/ending dates. A survey with only an arrival date cannot invent checkout; a customer-service survey is not stay evidence. |
| Room-ready notice | Prepared room/online check-in evidence. Keep date unknown unless stated; do not automatically mark completed. |
| Flight ticket issuance | Passenger relation, one row per segment, date, local times, real airport codes, marketing/operating carrier relationship, ticketed status. A two-passenger order is not two flights. Order price is recorded once. |
| Dining confirmation | Restaurant, stated date/time and party size, booking/cancellation status. Do not infer a Michelin award or completed meal. |

Do not choose the newest email indiscriminately. For the same explicitly identified stay, an actual lodging bill takes priority over planned dates; keep the plan as history. A changed checkout can also mean another room or another folio, so retain uncertain relationships. Consecutive reservations and visits with the same property name are not necessarily duplicates. Different names can be co-travelers, name changes or bookings for someone else: do not silently include/exclude them as the user's visits.

Export only the supported v1 hotel/flight/dining fields. Put other types, money, evidence links, badge candidates and unresolved comparisons in separate review artifacts. Do not silently add fields to the app contract or claim a badge has been written.

### Targeted follow-up for historical stays

After the first reconciliation, use its current ready manifest and the same private session to identify specific gaps. Supply the user's current local date for `--as-of`.

```bash
python3 scripts/plan_followups.py --session private/session.json --manifest private/results/latest.json --as-of 2024-05-01 --limit 20
```

The planner reads local files and prints a private task list. It prioritizes unresolved stay dates or conflicts and historical bookings with no post-stay verification. It also flags hotel stays with no linked final bill or invoice. It uses the dates in source observations when the current record has a date conflict. It treats planned dates on a completed record separately from dates actually supported by post-stay evidence. Keep the original authorized accounts, date scope and reading budget. A task is a search suggestion and has no effect on an existing acceptance decision.

For each selected task:

1. **Read pending sources first.** `read_candidates` lists discovered materials that still need reading or extraction. Inspect the original reservation, related attachments and any contradictory source already in the session. Resume an incomplete search at the checkpoint's saved cursor when the task says `resume_search`. Inspect `review_candidates` for recoverable retrieval gaps before referring them to the user.
2. **Search by the strongest available anchor.** Start with an exact, visible confirmation number or channel order reference in the authorized source account. Keep that reference private. Search both the booking channel and the hotel name when the order has a reseller. Use terms that match the evidence sought, such as `folio`, `invoice`, `thanks for staying`, `账单`, `水单`, `发票`, `cancellation confirmed`, or `已取消`. Use actual message bodies and attachments as evidence. Search terms alone cannot establish a cancellation or completed stay.
3. **Use dates to narrow a fallback.** For a final bill, search near the indicated checkout date with room for a later issue date. For cancellation or modification, search between booking and the planned stay when those dates are known. If the exact reference is missing or the first search finds nothing, try the property name or a corroborated alias plus a small date window within scope, then widen once if justified by an older folio or delayed invoice. Stay dates anchor searches and do not substitute for mail send dates. Include inline bills and attachment-only replies.
4. **Checkpoint and reconcile.** Use the task's `query_prefix` plus a descriptive suffix, such as `order-bill` or `property-cancel`, as the `query_id` in `run_session.py record-page`. Each account has its own cursor for that ID. Give a genuinely different query its own suffix. Record actual pages (including empty results), inventory useful attachments, mark inspected sources, and pass newly extracted observations to `reconcile_evidence.py`. Link a bill or cancellation only with evidence for the same order. Two similar stays can have separate orders, even if the property and dates match.

`searched` means the recorded attempts finished and their discovered candidates were handled. It may still show a gap. Skip identical completed attempts on continuation. A different query can be useful if there is a concrete lead, such as a newly found hotel alias. Stop at the selected reading budget and report active, searched and unresolved tasks separately. Finding no additional evidence in a bounded search leaves a booking at its existing status and price basis. Never claim that all relevant mailbox evidence has been found.

### Comparing an app export

Inspect the snapshot's actual storage before calling something new or missing. FotoNest's exported SQLite photo/place annotations do not necessarily include the account's separate `LocalTravelImport/.../records-v1.json` archive. Absence from annotations does not establish absence from all app records. Describe unmatched items as candidates until the relevant account archive is available. Record the snapshot identity and keep it read-only.

Match a place through its catalog identity or a corroborated alias. Do not merge different rooms/orders on property/date coincidence, or declare a same-property reservation to be a conflicting stay merely because its corresponding bill overlaps it; preserve an unresolved relationship when their identity is unproven. Keep completed evidence within its supported date scope and attach monetary observations without adding bill totals and payments together.

Separate proposals for adding records, appending evidence/room/amount information, confirmation badges, and unresolved source relationships. Follow the [selected acceptance profile](stay-acceptance.md): retaining same-hotel orders means missing room allocation or original booking order does not itself invalidate them, and stay-night counts use a date union. Adopt reservations without actual contrary evidence under that profile; do not equate unread material with a conflict or present the batch as a complete mailbox audit. A sender/contact/account owner's name alone is not a passenger or hotel-guest identity.

Preserve existing external source/record identities and their aliases across older exports, merged copies and stronger evidence. Inspect the current consumer before claiming replay behavior: a duplicate may reject an entire batch rather than silently skip that row. Preview generation and schema validation do not prove a real app import, semantic deduplication or badge/money support.

## 3. Account for every candidate

Create `coverage.json` with this shape:

```json
{
  "format": "fotonest.coverage.review",
  "version": 1,
  "expected_document_ids": ["body-a", "pdf-a"],
  "documents": [
    {"id": "body-a", "account": "mailbox-a", "kind": "email_body", "state": "parsed", "record_ids": ["stay-a"]},
    {"id": "pdf-a", "account": "mailbox-a", "kind": "attachment", "state": "needs_review", "reason": "OCR date columns remain ambiguous"}
  ]
}
```

The expected IDs come from the discovery/read inventory, not only successful extractions. `parsed` must reference an extracted record/evidence ID. `duplicate` needs `duplicate_of` pointing to another inventoried document; preserve its source provenance. `irrelevant` and `needs_review` need concrete reasons. An unresolved document is accounted for, but extraction is not complete.

```bash
python3 scripts/audit_coverage.py coverage.json
python3 scripts/validate_import.py export.fotonest.json
python3 scripts/validate_expenses.py spending.expenses.review.json
```

`audit_coverage.py` fails for missing/duplicate inventory entries, dangling duplicate links and malformed dispositions; it reports needs-review separately. It cannot prove search recall, factual accuracy or that a referenced record really contains the right values. Validate exported records independently, report gaps, and return review artifacts without writing to the app.

## Evaluation with user feedback

Use synthetic fixtures for public distribution; keep any real-mail evaluation local and authorized. A useful evaluation includes confirmations from old/new brands, localized ticket issuance, HTML-only surveys, inline bills, split PDF folios, cancellations/rebookings and other travelers. Compare property, each date, status, guest relation, currency, amount type and duplicate handling separately. A parser/format check is not an AI extraction accuracy score.

Ask the user only for ambiguous ground truth: who stayed, whether two orders were one trip/multiple rooms, or whether a cancellation was followed by another stay. Existing screenshots can seed a private answer sheet. Ask for additional examples only when they add a new failure mode; do not make users discover every missed email.

Helper regression checks (synthetic sources only):

```bash
python3 -m unittest discover -s tests -v
```

For an AI forward evaluation, give a fresh evaluator only the skill and synthetic sources. Ask it for a session, common evidence batch, v1 files and a spending review. Check interpretation independently, including a bill or cancellation after the first offer, a rerun before saving, and a rerun after a simulated partial save. Report helper behavior and AI extraction accuracy separately.

For an authorized real-mail evaluation, freeze the held-out messages and independent answers before reviewing evaluator output. Separate autonomous search results from extraction of explicitly supplied sources; a read cap can leave a discovered message unprocessed. Report denominators and unprocessed cases. A rerun after fixing a demonstrated failure is regression evidence, not a fresh blind accuracy result.
