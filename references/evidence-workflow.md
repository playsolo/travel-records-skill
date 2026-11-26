# Resumable evidence and pending imports

Use this protocol for multi-message imports and follow-up evidence. It works across direct hotels, airlines, agencies, OTAs, rewards portals, forwards and staff correspondence. The host AI uses authorized connectors to discover and interpret evidence. The scripts run locally. Use Python 3.9+ and install the v1 validator dependency with `python3 -m pip install jsonschema` in the Python environment where you run the scripts.

## Private session and discovery

Keep one private directory and stable, opaque namespace per import project. Do not reuse a provider booking number alone as a public record ID. Use opaque account/document/order keys; keep raw mail IDs and private source mappings inside the local inventory. Keep raw documents outside public Skill files. Files created by these scripts are mode 0600; new output directories are 0700. Existing directories retain their permissions. Use a single writer; concurrent session updates are unsupported.

Create `config.json`:

```json
{
  "namespace": "personal-travel-project",
  "accounts": ["mailbox-a", "mailbox-b"],
  "scope": {"description": "User-authorized source window and categories"},
  "profiles": {
    "stay_policy": "bill_priority_retain_same_property_orders",
    "spending_policy": "adopt_booking_price_without_contrary_evidence_bill_first",
    "traveler_scope": "user-selected-orders"
  }
}
```

The quoted-price profile is optional and represents the user's selected rule, not proof of payment. Omit it or use `documented_only` when unselected. `traveler_scope` expresses which orders the user wants compared, without requiring occupant investigation. Without it, unknown traveler relations do not prove a conflict. Missing-year completion is performed by the AI only when authorized: fill a missing hotel year from the original provider mail year, and retain `date_basis`; explicit dates and quoted original mail dates take precedence over forwarding dates.

```bash
python3 scripts/run_session.py init --session private/session.json --config private/config.json
python3 scripts/run_session.py record-page --session private/session.json --page private/page.json
python3 scripts/run_session.py next --session private/session.json --limit 20
python3 scripts/run_session.py mark --session private/session.json --update private/read.json
python3 scripts/run_session.py summary --session private/session.json
python3 scripts/run_session.py assert-complete --session private/session.json
```

`page.json` describes one actual connector page; `page_token` must explicitly be `null` for the first page. Never manufacture a completed cursor after hitting a read cap.

```json
{
  "account": "mailbox-a", "query_id": "hotel-window-1", "query": "authorized query",
  "page_token": null, "next_page_token": "opaque-next-page",
  "items": [
    {"id": "body-a", "kind": "email_body", "source_id": "opaque-provider-message"},
    {"id": "folio-a", "kind": "attachment", "source_id": "opaque-attachment", "parent_id": "body-a"}
  ]
}
```

Document IDs are unique across accounts; account-scope them yourself. Page replay is idempotent and cannot rewind a later cursor. `read.json` is `{"document_id":"body-a","state":"read"}`. Supported states: `needs_read`, `read`, `parsed`, `duplicate`, `irrelevant`, `needs_review`. Parsed needs `record_ids`; duplicate needs an existing `duplicate_of`; irrelevant/review need a concrete `reason`. Read without extraction remains pending. Reopening a terminal disposition requires `needs_review` and a reason. For screenshots/documents provided outside mail, inventory them with their corresponding kinds through the same page mechanism, using a descriptive query and no pagination.

An inventoried item may include `"priority":"transaction"` when observed metadata identifies a transaction candidate; omit it for normal priority. This is an AI-supplied scheduling hint, not a keyword parser or extraction allowlist. Keep it stable on page replay. Existing v1 sessions without this field retain normal priority. `next` selects fresh read-but-unextracted materials first, then attachments, transaction-priority bodies, normal sources, and retryable failures. It never marks a source read or moves its cursor merely by returning it.

Record an actual failed operation with `failure`, rather than repeatedly returning the same failed item at the front of the queue:

```json
{
  "document_id": "folio-a", "failure_id": "opaque-attempt-1", "action": "read",
  "reason": "connector transport closed", "retryable": true, "max_attempts": 3
}
```

```bash
python3 scripts/run_session.py failure --session private/session.json --update private/failure.json
```

Use a new opaque `failure_id` for each actual failed attempt and replay the same ID when retrying a checkpoint write whose outcome was uncertain. Identical replay does not consume another attempt or undo subsequent recovery, including after a later operation. `action` is `read`, `extract` or `review`; `max_attempts` bounds failed attempts for that operation (default 3), not the task's total reading budget. Record only a concise operational reason, not connector credentials or raw mail. Successful reads/extractions use the existing `mark`/reconciliation path. Explicit document dispositions deactivate the current retry while retaining failure history, so a later semantic review cannot revive an old read failure. No script invokes a connector, retries network calls or restarts the host.

Retryable failures remain available after fresh work. Exhausted or non-retryable failures move out of `next.documents` into `blocked_documents`; semantic review items without an automatic next action appear in `review_documents`. Both lists are samples bounded by `--limit`; use `processing` counts and the saved session for the full queue. Inspect these items separately, seek additional evidence or report the blocker; do not discard them or loop forever on an unchanged error. Legacy `needs_review` reasons `unread_source` and `read_without_extraction` remain actionable. Other existing review reasons require explicit review rather than an invented retry history.

`summary`, `next`, the reconciliation review and `latest.json` expose the same derived `processing` status: `not_started`, `partial`, `needs_review`, `blocked` or `complete`. Unfinished query pagination, accounts with no registered query, unread sources and outstanding extraction/retry actions prevent completion. Review items and exhausted failures cannot be counted as fully resolved. `assert-complete` reads the session without changing it and returns exit 0 only for `complete`, exit 2 for unfinished work and a nonzero error for invalid input. Even a successful empty search must be registered for each authorized account. This checks registered work only; it cannot prove the search strategy found every travel email or that fields are factually correct. Complete requested follow-up searches and independently review the evidence before calling the user-requested scope fully verified.

Detected reconciliation conflicts and pending financial units also prevent completion, even when their source documents are already parsed. Reconciliation persists these review counts in the session so the CLI and manifest agree; new evidence can resolve them on the next reconciliation. Existing v1 reconciliation checkpoints without this derived summary require an empty-batch reconciliation to refresh it before completion can pass. Replaying old evidence alone does not clear an explicit document review; resolve it explicitly after checking the evidence. Proposed updates to existing App rows and unverified import receipts remain separate delivery concerns and do not require App mutation to finish extraction.

## AI extraction batch

Read the actual body and relevant attachments, then write `fotonest.evidence.batch` v1. Interpret unfamiliar templates semantically, without provider allowlists. This is a local intermediate format, not the App's v1 file.

```json
{
  "format": "fotonest.evidence.batch", "version": 1,
  "observations": [{
    "id": "observation-a", "document_id": "body-a",
    "identity_keys": ["opaque-order-a:hotel-stay"],
    "identity_evidence": "Provider explicitly links this confirmation to the same order",
    "role": "reservation",
    "booked_at": "2024-01-01T10:00:00Z",
    "property_key": "corroborated-property-a", "room_count": 1,
    "date_basis": {"start": "explicit", "end": "explicit"},
    "record": {
      "kind": "hotel", "title": "Example Hotel", "status": "reserved",
      "start": "2024-02-01", "end": "2024-02-03",
      "evidence": {"title": "Example Hotel", "status": "Reservation confirmed",
                   "start": "Check in February 1, 2024", "end": "Check out February 3, 2024"}
    }
  }],
  "same_record": [],
  "amounts": [{
    "id": "quote-a", "financial_unit": "opaque-consumption-a",
    "observation_ids": ["observation-a"], "amount": "200.00", "currency": "USD",
    "basis": "booking_total", "source": "body-a", "evidence": "Total price USD 200.00"
  }]
}
```

Observation fields:

| Field | Meaning |
| --- | --- |
| `id`, `document_id`, `role`, `record` | Required. Observation ID is immutable; changed extraction needs a new ID and explicit revision link. The `record` contains v1 fields except generated `id`/`source`. |
| `identity_keys`, `identity_evidence` | Optional opaque logical identity keys and required supporting reason when keys are used. Cross-account copies share a key only with evidence. Hotel name/date coincidence does not establish identity. |
| `same_record` | Optional batch list of `{"from":"observation-a","to":"observation-b","basis":"explicit corresponding-order link"}`. Use for supported source links discovered later. |
| `supersedes`, `supersedes_evidence` | Optional prior observation IDs and explicit revision reason. This also links identity. Keep both observations; exclude the superseded version from current-field selection. Dangling/cyclic revisions fail. |
| `event_at`, `event_at_basis` | Optional original offset timestamp, with basis `original_provider_event` or `original_message_date`. Never use fetch/forward time to win conflicts. If equal-priority field values differ, only a unique later original event can choose between them; otherwise review. |
| `booked_at` | Optional original booking offset timestamp. Earliest linked original booking time is used for comparison with other hotels. A reminder's send time is not a booking time. |
| `property_key`, `traveler_scope` | Optional corroborated property and user-selected comparison scope. Distinct orders at the same property are retained. Unknown property identity cannot establish that two hotels conflict. |
| `room_count`, `party_size`, `local_start_time`, `timezone` | Optional positive integer quantities, HH:mm and IANA timezone metadata. Keep timezone provenance truthful; do not infer physical attendance. These never enter v1 export. |
| `date_basis` | Optional start/end values `explicit` or `original_email_year`. Record the actual completion decision; scripts do not infer dates from raw mail. |

Role/status pairs are fixed: reservation/modification → reserved; cancellation → cancelled; stay_evidence → completed; processing → processing; unknown → unknown. Only actual lodging bills or appropriate post-stay statements warrant hotel stay_evidence. Flight ticket/payment/boarding-pass issuance and dining confirmation remain reserved unless completion is separately supported. Confirmed bookings with missing dates remain recognizable, but unknown nights are not invented.

A booking key must identify **one logical component**: two flight legs need different keys even when they share a PNR; two independent hotel orders need different keys even when they share a message. Marketing and operating carriers for the same leg share its identity. An explicit reissue changing the same leg uses a new observation linked to the old component. Do not merge old/new routes solely by airport/date similarity.

Current values prioritize stay_evidence, cancellation, reservation/modification, processing, unknown. Explicit supersession takes precedence. Nonconflicting lower-priority fields can fill gaps with provenance. Kind conflicts across linked history remain reviewable. A completed hotel badge candidate includes only actual/post-stay date evidence, never planned dates filled from a reservation.

## Price recognition

Amount observations require distinct immutable `id`, `financial_unit`, nonempty `observation_ids`, decimal-string `amount`, ISO3 `currency` (or null), `basis`, inventoried `source`, and short `evidence`. Optional `supersedes` refers to amount IDs in the same financial unit. Identity of consumption must be explicitly supported: do not join bills by property/date or identical prices.

Supported bases: `bill_total`, `invoice_total`, `payment_total`, `booking_total`, `nightly_rate_per_room`, `deposit`, `balance`, `refund`, `tax_component`, `loyalty_points`, `unbooked_quote`, `penalty`.

- Bill/invoice total wins over a whole-order payment, booking total, then per-room nightly rate. Stronger currency replaces weaker currency without invented FX. Corresponding sources count once per financial unit, including an order covering several flight legs.
- Booking total is adopted only under the selected quoted-price profile. Nightly rate needs one hotel, full dates and explicit room count. Its original quantities must match current quantities; changed/unknown rate quantities remain pending unless a stronger total resolves them. Whole-order totals are never multiplied by rooms.
- Independent units add even with identical dates and amounts. Stay nights use accepted date union, excluding checkout, regardless of rooms.
- Equal-priority contradictory totals need explicit revision or review. Different record allocations, partial cancellation, unknown currency and refunds remain pending. Deposits, zero balances, tax components, points, penalties and unbooked optional prices do not add to recognized spending. A bill for an unaccepted/cancelled order remains reviewable.
- `payment_total` means an explicitly linked whole-order amount, not any payment-card transaction. AI must preserve the amount's scope. No tax split, card number or occupant audit is required.

The helper can also be used independently: `python3 scripts/recognize_spending.py private/spending-input.json --output private/spending-review.json`. Its `fotonest.spending.input` v1 has `policy`, `records` (`id`, `kind`, `accepted`, `status`, optional dates/rooms/property/title), and `amounts` as above with `record_ids` instead of `observation_ids`. The output is `fotonest.spending.recognition`, separate from the legacy raw `expenses-review.schema.json` ledger; do not validate one as the other.

## Reconcile, review and resume

```bash
python3 scripts/reconcile_evidence.py --session private/session.json --batch private/evidence.json --output-dir private/results
```

The session retains observations, explicit links, stable UUID identities, offered record versions and confirmed saves. Observation and amount IDs cannot be edited in place. Up to 5,000 observations, amounts and links each are supported per session. Split large imports into meaningful scopes and align cross-scope identities before import. Missing source or relationship references fail without persisting the batch. Parsed dispositions show which documents produced evidence.

Read `private/results/latest.json` after each successful run. For independent review or reuse in another tool, start with `review_file`. The `import_files` entries are for FotoNest.

For delivery, use the actual saved `review_file` and write the travel CSV from that same review. Use the user's requested destination or a private workspace output directory outside version control. Reopen the JSON and CSV, check that the CSV covers the intended records and recognized amounts, and give the user links to the files. A progress update can show a preview in chat. When delivering partial results, label the files with the scope already checked and preserve the checkpoint for continuation.

- `import_files` lists the current records awaiting import in v1 batches of at most 100. An unchanged rerun keeps offering pending records with the same IDs. A bill arriving before a save refreshes the pending record under its original ID. `ready_to_import` counts all rows in the current files. `added` counts first-time offers in this run.
- `review_file` includes the current records, source history, date provenance, spending, nights and unresolved evidence. For a confirmed save, later corrections appear under `delta.updated` for manual review. A merge involving more than one saved or unverified legacy identity stays in review until the App identities are resolved.
- Processing/unknown states, conflicting fields and unsupported v1 date ranges are held. Existing planned history remains in the session. App v1 cannot represent timezones/precise local times or reversed local-date ranges across the date line; those stay in review.
- Coverage distinguishes discovered/read/parsed and unresolved documents. Complete query pagination does not prove mailbox recall. Format checks do not prove AI accuracy, real App import, badges or monetary support.

### Record the saves FotoNest completed

After an import attempt, record the IDs the user actually saved. Selecting a file opens a review queue, and a partial save can leave some rows pending. Use the exact v1 file the user opened, including an older file if they saved from it. Leave uncertain rows out of the receipt and verify the save outcome before offering another file.

```json
{
  "format": "fotonest.import.results", "version": 1,
  "saved": [{
    "file": "/absolute/path/to/results/run-example/new-001.fotonest.json",
    "ids": ["saved-record-id-from-that-file"]
  }]
}
```

```bash
python3 scripts/reconcile_evidence.py --session private/session.json --output-dir private/results --import-results private/import-results.json
```

You can also pass `--batch` to add new evidence in the same run. Omit it to use the evidence already in the checkpoint. The same save receipt can be retried safely. After an interrupted run with an `in_progress` manifest, rerun with the same inputs and use the files from the next `ready` manifest. Keep historical files to document which versions were offered and saved.

Sessions from versions that tracked file generation alone list old exports under `delta.legacy_unverified_ids`. Verify each affected ID against the relevant FotoNest account. Record a saved ID with its original file, or use `"legacy_not_saved_ids": ["verified-unsaved-id"]` in the same results format after verifying that a row was never saved. Unverified legacy rows stay on hold. New sessions use the same namespace and checkpoint throughout their own import and still need identity alignment for records created elsewhere.
