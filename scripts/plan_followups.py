#!/usr/bin/env python3
"""Plan targeted hotel evidence checks from a completed local reconciliation."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path

import run_session

ACTION_ORDER = {'read_candidates': 0, 'resume_search': 1, 'start_search': 2,
                'review_candidates': 3, 'searched': 4}
DATE_CONFLICTS = {'start', 'end', 'property_key'}
STAY_CONFLICTS = {'conflicting_stay_evidence', 'conflicts_with_stay_evidence',
                  'booking_order_unknown_or_tied', 'superseded_by_later_booking'}
FINAL_BASIS = {'bill_total', 'invoice_total'}


def full_date(value):
    if isinstance(value, str) and len(value) == 10:
        return date.fromisoformat(value)
    return None


def query_prefix(record_id):
    key = hashlib.sha256(record_id.encode('utf-8')).hexdigest()[:24]
    return f'followup-hotel-{key}:'


def matching_checkpoint(session, review):
    """Discovery may advance between reconciliations; the evidence must match."""
    checkpoint = session.get('reconciliation', {})
    if review.get('format') != 'fotonest.reconciliation.review' or review.get('version') != 1:
        raise ValueError('expected reconciliation review')
    for output_key, state_key in [('source_observations', 'observations'),
                                  ('record_links', 'same_record'),
                                  ('amount_observations', 'amounts')]:
        if review.get(output_key, []) != checkpoint.get(state_key, []):
            raise ValueError('review does not match checkpoint')
    source = 'fotonest-import:' + session['namespace']
    if any(item['record']['source'] != source for item in review['records']):
        raise ValueError('review from another session')


def followup_action(attempts, documents, children):
    refs = {ref for attempt in attempts for page in attempt['pages'] for ref in page['document_ids']}
    # Attachments may be discovered later than their parent message.
    queued = list(refs)
    while queued:
        ref = queued.pop()
        nearby = children.get(ref, [])
        duplicate_of = documents[ref].get('duplicate_of')
        if duplicate_of:
            nearby = [*nearby, duplicate_of]
        for other in nearby:
            if other not in refs:
                refs.add(other)
                queued.append(other)
    to_read = sorted(ref for ref in refs if documents[ref]['state'] in {'needs_read', 'read'})
    to_review = sorted(ref for ref in refs if documents[ref]['state'] == 'needs_review')
    if to_read:
        action = 'read_candidates'
    elif any(not attempt['complete'] for attempt in attempts):
        action = 'resume_search'
    elif to_review:
        action = 'review_candidates'
    elif attempts:
        action = 'searched'
    else:
        action = 'start_search'
    return action, to_read, to_review


def plan(session, review, as_of, limit):
    matching_checkpoint(session, review)
    if not 1 <= limit <= 500:
        raise ValueError('invalid follow-up limit')
    docs = {d['id']: d for d in session['documents']}
    children = {}
    for doc in docs.values():
        children.setdefault(doc.get('parent_id'), []).append(doc['id'])
    observations = {o['id']: o for o in review['source_observations']}
    billed = {ref for a in review['amount_observations'] if a['basis'] in FINAL_BASIS
              for ref in a['observation_ids']}
    checkpoint = session.get('reconciliation', {})
    assignments = checkpoint.get('assignments', {})
    legacy_merges = checkpoint.get('merge_blocks', {})
    today = as_of.isoformat()
    by_prefix = {}
    for q in session['queries']:
        prefix, separator, variant = q['query_id'].partition(':')
        if prefix.startswith('followup-hotel-') and separator and variant:
            by_prefix.setdefault(prefix + separator, []).append(q)
    tasks = []
    for item in review['records']:
        row = item['record']
        if row.get('kind') != 'hotel' or row.get('status') not in {'reserved', 'completed'}:
            continue
        refs = item['observation_ids']
        # Recover date anchors from source observations when reconciliation held a field.
        spans = {(o['record'].get('start'), o['record'].get('end')) for ref in refs
                 if (o := observations[ref])['role'] in {'reservation', 'modification', 'stay_evidence'}}
        # A prior month/year is a useful anchor even when a day is unknown.
        historical_spans = [(start, end) for start, end in spans
                            if any(value and value < today[:len(value)] for value in (start, end))]
        if row['status'] == 'reserved' and not historical_spans:
            continue
        actual = item['badge_candidates']
        actual_dates_complete = any(full_date(b.get('start')) and full_date(b.get('end')) for b in actual)
        end = full_date(row.get('end'))
        reasons = []
        if DATE_CONFLICTS.intersection(item['conflicts']) or item['acceptance']['reason'] in STAY_CONFLICTS:
            reasons.append('resolve_stay_conflict')
        if row['status'] == 'completed' and not actual_dates_complete:
            reasons.append('complete_actual_dates')
        if row['status'] == 'reserved':
            if not full_date(row.get('start')) or not end:
                reasons.append('complete_planned_dates')
            if end and end < as_of:
                reasons.append('verify_past_reservation')
        if (row['status'] == 'completed' or 'verify_past_reservation' in reasons) and not billed.intersection(refs):
            reasons.append('find_final_bill')
        if not reasons:
            continue
        prefix = query_prefix(item['id'])
        # When linked records acquire a canonical ID, keep the cursors of both.
        record_ids = {item['id']} | {assignments[ref] for ref in refs if ref in assignments}
        record_ids.update(old for rid in list(record_ids) for old in legacy_merges.get(rid, []))
        attempts = [q for rid in sorted(record_ids) for q in by_prefix.get(query_prefix(rid), [])]
        action, to_read, to_review = followup_action(attempts, docs, children)
        sources = sorted({observations[ref]['document_id'] for ref in refs})
        tasks.append(dict(record_id=item['id'], title=row.get('title'), reasons=reasons, action=action,
                          stay_dates=[dict(start=start, end=end) for start, end in
                                      sorted(historical_spans, key=lambda pair: tuple(v or '' for v in pair))[:8]],
                          source_document_ids=sources, source_accounts=sorted({docs[ref]['account'] for ref in sources}),
                          query_prefix=prefix, queries=[dict(account=q['account'], query_id=q['query_id'],
                                                              complete=q['complete']) for q in attempts],
                          pending_document_ids=to_read, review_document_ids=to_review))
    tasks.sort(key=lambda task: (ACTION_ORDER[task['action']],
                                 task['reasons'] == ['find_final_bill'],
                                 'resolve_stay_conflict' not in task['reasons'],
                                 'complete_actual_dates' not in task['reasons'], task['record_id']))
    return dict(format='fotonest.hotel.followups', version=1, as_of=as_of.isoformat(),
                total=len(tasks), counts_by_action=dict(Counter(task['action'] for task in tasks)),
                tasks=tasks[:limit])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--manifest', required=True, help='current latest.json from reconciliation')
    parser.add_argument('--as-of', required=True, type=date.fromisoformat, help='local calendar date, YYYY-MM-DD')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    try:
        session = run_session.load_session(args.session)
        with Path(args.manifest).open(encoding='utf-8') as handle:
            manifest = json.load(handle)
        if manifest['state'] != 'ready':
            raise ValueError('manifest must be ready')
        with Path(manifest['review_file']).open(encoding='utf-8') as handle:
            review = json.load(handle)
        result = plan(session, review, args.as_of, args.limit)
    except (ValueError, KeyError, TypeError, OSError):
        raise SystemExit('INVALID: use the current ready reconciliation manifest and its matching session')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
