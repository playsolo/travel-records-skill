#!/usr/bin/env python3
"""Reconcile AI-extracted evidence locally and export records awaiting app import."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import re
import uuid

import audit_coverage
import recognize_spending
import resolve_stays
import run_session
import validate_import

ROLES = {'unknown': 0, 'processing': 1, 'reservation': 2, 'modification': 2,
         'cancellation': 3, 'stay_evidence': 4}
STATUSES = {'unknown': 'unknown', 'processing': 'processing', 'reservation': 'reserved',
            'modification': 'reserved', 'cancellation': 'cancelled', 'stay_evidence': 'completed'}
META = ('property_key', 'traveler_scope', 'room_count', 'party_size', 'local_start_time', 'timezone')


def fields(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= obj.keys() or obj.keys() - set(required) - set(optional):
        raise ValueError('invalid fields')


def ident(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError('invalid opaque identifier')
    return value


def stamp(value):
    if not isinstance(value, str): raise ValueError('invalid timestamp')
    result = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('timestamp requires offset')
    return result


def validate_observation(o, documents):
    fields(o, ['id', 'document_id', 'role', 'record'],
           ['identity_keys', 'identity_evidence', 'event_at', 'event_at_basis', 'supersedes',
            'supersedes_evidence', 'booked_at', 'date_basis', *META])
    ident(o['id'])
    if o['document_id'] not in documents or o['role'] not in ROLES: raise ValueError('invalid source or role')
    keys = o.get('identity_keys', [])
    if not isinstance(keys, list) or len(set(keys)) != len(keys): raise ValueError('invalid identities')
    for k in keys: ident(k)
    if keys: ident(o.get('identity_evidence'))
    previous = o.get('supersedes', [])
    if not isinstance(previous, list) or len(set(previous)) != len(previous): raise ValueError('invalid supersedes')
    for p in previous: ident(p)
    if previous: ident(o.get('supersedes_evidence'))
    if 'event_at' in o:
        stamp(o['event_at'])
        if o.get('event_at_basis') not in ['original_provider_event', 'original_message_date']:
            raise ValueError('event timestamp needs original basis')
    elif 'event_at_basis' in o: raise ValueError('timestamp missing')
    if 'booked_at' in o: stamp(o['booked_at'])
    for k in ('property_key', 'traveler_scope', 'timezone'):
        if k in o: ident(o[k])
    for k in ('room_count', 'party_size'):
        if k in o and (type(o[k]) is not int or not 1 <= o[k] <= 10000): raise ValueError('invalid quantity')
    if 'local_start_time' in o and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', o['local_start_time']):
        raise ValueError('invalid local time')
    if 'date_basis' in o:
        fields(o['date_basis'], [], ['start', 'end'])
        if any(v not in ['explicit', 'original_email_year'] for v in o['date_basis'].values()):
            raise ValueError('invalid date basis')
    r = o['record']
    fields(r, ['kind', 'title', 'status', 'evidence'], ['start', 'end', 'origin', 'destination'])
    if r['status'] != STATUSES[o['role']]: raise ValueError('role/status mismatch')
    # Validate each date independently. Unsupported ranges remain reviewable evidence.
    for omit in ('start', 'end'):
        row = {**r, 'id': 'validation', 'source': 'validation'}
        row.pop(omit, None)
        validate_import.validate(dict(format='fotonest.travel', version=1, records=[row]))


def append_immutable(old, new):
    by_id = {x['id']: x for x in old}
    for x in new:
        if x['id'] in by_id and by_id[x['id']] != x: raise ValueError('immutable evidence changed; use a revision')
        by_id[x['id']] = copy.deepcopy(x)
    return [by_id[k] for k in sorted(by_id)]


def choose(candidates, getter):
    available = [(o, getter(o)) for o in candidates if getter(o) is not None]
    if not available: return None, [], False
    rank = max(ROLES[o['role']] for o, _ in available)
    best = [(o, v) for o, v in available if ROLES[o['role']] == rank]
    if len({json.dumps(v, sort_keys=True) for _, v in best}) > 1:
        if not all('event_at' in o for o, _ in best): return None, [], True
        latest = max(stamp(o['event_at']) for o, _ in best)
        best = [(o, v) for o, v in best if stamp(o['event_at']) == latest]
        if len({json.dumps(v, sort_keys=True) for _, v in best}) > 1: return None, [], True
    return best[0][1], [o['id'] for o, _ in best], False


def record_digest(record):
    encoded = json.dumps(record, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def read_json(path, limit):
    with Path(path).open('rb') as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError('input too large')
    return json.loads(data)


def import_results(state, source, results):
    """Record explicit user verification for individual rows of past export files."""
    fields(results, ['format', 'version'], ['saved', 'legacy_not_saved_ids'])
    if results['format'] != 'fotonest.import.results' or type(results['version']) is not int or results['version'] != 1:
        raise ValueError('invalid import results')
    saved = results.get('saved', [])
    not_saved = results.get('legacy_not_saved_ids', [])
    if not isinstance(saved, list) or len(saved) > 5000 or not isinstance(not_saved, list) or len(not_saved) > 5000:
        raise ValueError('invalid import result lists')
    confirmed = state['confirmed_imports']
    legacy = state['legacy_exports']
    for entry in saved:
        fields(entry, ['file', 'ids'])
        if not isinstance(entry['file'], str) or not entry['file'].strip():
            raise ValueError('missing export path')
        ids = entry['ids']
        if not isinstance(ids, list) or not ids or len(ids) > 100:
            raise ValueError('invalid confirmed IDs')
        ids = [ident(rid) for rid in ids]
        if len(set(ids)) != len(ids):
            raise ValueError('duplicate confirmed ID')
        data = read_json(entry['file'], 2 * 1024 * 1024)
        validate_import.validate(data)
        rows = {r['id']: r for r in data['records'] if r['source'] == source}
        for rid in ids:
            if rid not in rows:
                raise ValueError('confirmed record was not in this session export')
            row = rows[rid]
            was_legacy_export = legacy.get(rid) == row
            if not was_legacy_export and record_digest(row) not in state['offered_versions'].get(rid, []):
                raise ValueError('confirmed record version was not exported')
            if rid in confirmed and confirmed[rid] != row:
                raise ValueError('conflicting versions for the same saved record')
            confirmed[rid] = row
    checked = set(state['legacy_not_saved_ids'])
    for rid in not_saved:
        ident(rid)
        if rid not in legacy or rid in confirmed:
            raise ValueError('invalid legacy not-saved result')
        checked.add(rid)
    state['legacy_not_saved_ids'] = sorted(checked - confirmed.keys())


def reconcile(session, batch, results=None):
    """Return (updated session, review, current unsaved records) without mutating inputs."""
    from jsonschema import ValidationError

    fields(batch, ['format', 'version', 'observations'], ['same_record', 'amounts'])
    if batch['format'] != 'fotonest.evidence.batch' or type(batch['version']) is not int or batch['version'] != 1:
        raise ValueError('invalid batch')
    s = copy.deepcopy(session)
    ident(s['namespace'])
    if len(s['namespace']) > 100: raise ValueError('namespace too long')
    source = 'fotonest-import:' + s['namespace']
    state = s.setdefault('reconciliation', dict(observations=[], same_record=[], amounts=[], assignments={}))
    # Old sessions recorded file generation only. Hold those identities until checked.
    if 'generated' in state:
        state['legacy_exports'] = state.pop('generated')
    state.setdefault('legacy_exports', {})
    state.setdefault('legacy_not_saved_ids', [])
    state.setdefault('confirmed_imports', {})
    state.setdefault('offered_versions', {})
    if results is not None:
        import_results(state, source, results)
    confirmed = state['confirmed_imports']
    legacy_unverified = state['legacy_exports'].keys() - set(state['legacy_not_saved_ids']) - confirmed.keys()
    previous_observation_ids = {o['id'] for o in state['observations']}
    for key in ['observations', 'same_record', 'amounts']:
        incoming = batch.get(key, [])
        if not isinstance(incoming, list) or len(incoming) > 5000: raise ValueError('batch too large')
        if key != 'same_record':
            if any(not isinstance(x, dict) or not isinstance(x.get('id'), str) for x in incoming): raise ValueError('invalid evidence')
            if len({x['id'] for x in incoming}) != len(incoming): raise ValueError('duplicate evidence IDs')
            state[key] = append_immutable(state[key], incoming)
        else:
            for link in incoming:
                fields(link, ['from', 'to', 'basis']); ident(link['basis'])
                if link not in state[key]: state[key].append(copy.deepcopy(link))
        if len(state[key]) > 5000: raise ValueError('session too large; split scope')
    docs = {d['id']: d for d in s['documents']}
    obs = {o['id']: o for o in state['observations']}
    for o in obs.values(): validate_observation(o, docs)
    parent = {k: k for k in obs}
    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]; k = parent[k]
        return k
    def union(a, b):
        if a not in obs or b not in obs: raise ValueError('dangling record link')
        a, b = find(a), find(b); parent[max(a, b)] = min(a, b)
    identities = {}
    for o in obs.values():
        for key in o.get('identity_keys', []):
            if key in identities: union(o['id'], identities[key])
            identities[key] = o['id']
        for previous in o.get('supersedes', []): union(o['id'], previous)
    for link in state['same_record']: union(link['from'], link['to'])
    # Kahn traversal rejects cycles without recursion depth dependence.
    remaining = {k: set(o.get('supersedes', [])) for k, o in obs.items()}
    while remaining:
        ready = {k for k, deps in remaining.items() if not deps}
        if not ready: raise ValueError('supersession cycle')
        remaining = {k: deps - ready for k, deps in remaining.items() if k not in ready}
    superseded = {p for o in obs.values() for p in o.get('supersedes', [])}
    groups = {}
    for k in sorted(obs): groups.setdefault(find(k), []).append(obs[k])
    current, pending, merges = [], [], []
    current_assignments = {}
    ns = uuid.uuid5(uuid.NAMESPACE_URL, 'fotonest:' + s['namespace'])
    for members in groups.values():
        old_ids = {state['assignments'][o['id']] for o in members if o['id'] in state['assignments']}
        # Older versions overwrote merged assignments. Retain the previously recorded lineage.
        old_merges = state.get('merge_blocks', {})
        old_ids.update(previous for rid in list(old_ids) for previous in old_merges.get(rid, []))
        keys = [k for o in members for k in o.get('identity_keys', [])]
        anchor = 'identity:' + min(keys) if keys else 'observation:' + min(o['id'] for o in members)
        protected = sorted(old_ids & (confirmed.keys() | legacy_unverified))
        offered = sorted(old_ids & (state['offered_versions'].keys() | state['legacy_exports'].keys()))
        rid = (protected or offered or sorted(old_ids) or [str(uuid.uuid5(ns, 'anchor:' + anchor))])[0]
        for o in members:
            state['assignments'].setdefault(o['id'], rid)
            current_assignments[o['id']] = rid
        active = [o for o in members if o['id'] not in superseded]
        row = dict(id=rid, source=source, evidence={})
        provenance, conflicts, metadata = {}, [], {}
        for field in ['kind', 'title', 'status', 'start', 'end', 'origin', 'destination', *META]:
            getter = (lambda o, f=field: o.get(f)) if field in META else (lambda o, f=field: o['record'].get(f))
            value, refs, conflict = choose(active, getter)
            if conflict: conflicts.append(field)
            if value is not None:
                (metadata if field in META else row)[field] = value
                provenance[field] = refs
                if field not in META and field != 'kind':
                    evidence = obs[refs[0]]['record']['evidence'].get(field)
                    if evidence: row['evidence'][field] = evidence
        if len({o['record']['kind'] for o in members}) > 1: conflicts.append('kind_history')
        booked = [o['booked_at'] for o in members if o.get('booked_at')]
        if booked: metadata['booked_at'] = min(booked, key=stamp)
        badges = []
        # Never fill an actual badge's dates from a reservation.
        actual = [o for o in active if o['role'] == 'stay_evidence']
        if actual and row.get('kind') == 'hotel' and not conflicts:
            badge = {'property_key': metadata.get('property_key'), 'source_observation_ids': [o['id'] for o in actual]}
            for field in ['start', 'end']:
                value, _, conflict = choose(actual, lambda o, f=field: o['record'].get(f))
                if value is not None and not conflict: badge[field] = value
            badges.append(badge)
        if len(protected) > 1:
            merges.append(dict(id=rid, previous_ids=protected, reason='existing_identities_require_manual_alignment'))
            conflicts.append('identity_merge')
        try: validate_import.validate(dict(format='fotonest.travel', version=1, records=[row]))
        except (ValueError, ValidationError):
            # Unsupported v1 projections remain in review, without exposing excerpts.
            conflicts.append('v1_projection_invalid')
        if row.get('status') in ['processing', 'unknown']: conflicts.append('unconfirmed_status')
        item = dict(id=rid, record=row, metadata=metadata, field_sources=provenance,
                    observation_ids=[o['id'] for o in members], badge_candidates=badges, conflicts=sorted(set(conflicts)))
        current.append(item)
        if conflicts: pending.append(dict(id=rid, reasons=item['conflicts']))
    current.sort(key=lambda x: x['id'])
    stays = []
    for item in current:
        r, m = item['record'], item['metadata']
        if r.get('kind') == 'hotel' and not item['conflicts']:
            stays.append(dict(id=r['id'], property_key=m.get('property_key'), traveler_scope=m.get('traveler_scope', s['profiles'].get('traveler_scope')),
                              start=r.get('start'), end=r.get('end'), booked_at=m.get('booked_at'),
                              evidence_kind='stay_evidence' if r['status'] == 'completed' else 'reservation', cancelled=r['status'] == 'cancelled'))
    policy = s['profiles'].get('stay_policy', resolve_stays.RETAIN_ORDERS_POLICY)
    acceptance = resolve_stays.resolve(dict(policy=policy, stays=stays))
    decisions = {d['id']: d for d in acceptance['decisions']}
    for item in current:
        r = item['record']
        item['acceptance'] = decisions.get(item['id'], dict(id=item['id'], acceptance='needs_review' if item['conflicts'] else 'not_accepted' if r.get('status') == 'cancelled' else 'accepted', reason='source_state'))
        if item['acceptance']['acceptance'] == 'needs_review' and not item['conflicts']:
            pending.append(dict(id=item['id'], reasons=[item['acceptance']['reason']]))
    money = []
    for a in state['amounts']:
        fields(a, ['id', 'financial_unit', 'observation_ids', 'amount', 'currency', 'basis', 'source', 'evidence'], ['supersedes'])
        refs = a['observation_ids']
        if not isinstance(refs, list) or not refs or len(set(refs)) != len(refs) or any(k not in obs for k in refs) or a['source'] not in docs:
            raise ValueError('invalid amount source or allocation')
        value = {k: v for k, v in a.items() if k != 'observation_ids'}
        value['record_ids'] = sorted({current_assignments[k] for k in refs})
        money.append(value)
    spending = recognize_spending.recognize(dict(format='fotonest.spending.input', version=1,
        policy=s['profiles'].get('spending_policy', 'documented_only'), amounts=money,
        records=[dict(id=i['id'], kind=i['record'].get('kind', 'hotel'), status=i['record'].get('status', 'unknown'),
                      accepted=i['acceptance']['acceptance'] == 'accepted',
                      **{k: i['record'].get(k) for k in ['start', 'end']},
                      room_count=i['metadata'].get('room_count')) for i in current]))
    # A rate's original quantities cannot be replaced by later bill/room metadata.
    for recognized in list(spending['recognized']):
        if recognized['basis'] != 'nightly_rate_per_room': continue
        item = next(i for i in current if i['id'] == recognized['record_ids'][0])
        canonical = (item['record'].get('start'), item['record'].get('end'), item['metadata'].get('room_count'))
        superseded_amounts = {p for a in state['amounts'] for p in a.get('supersedes', [])}
        rates = [a for a in state['amounts'] if a['financial_unit'] == recognized['financial_unit'] and a['basis'] == 'nightly_rate_per_room' and a['id'] not in superseded_amounts]
        if any((obs[k]['record'].get('start'), obs[k]['record'].get('end'), obs[k].get('room_count')) != canonical for a in rates for k in a['observation_ids']):
            spending['recognized'].remove(recognized)
            spending['pending'].append(dict(financial_unit=recognized['financial_unit'], reason='rate_quantity_changed_or_unknown'))
    from decimal import Decimal
    totals = {}
    for r in spending['recognized']: totals[r['currency']] = totals.get(r['currency'], Decimal(0)) + Decimal(r['amount'])
    spending['totals_by_currency'] = {k: format(v, 'f') for k, v in sorted(totals.items())}
    added, updated, unchanged, exports = [], [], [], []
    for item in current:
        rid = item['id']; old = confirmed.get(rid)
        if rid in legacy_unverified:
            continue
        if item['conflicts'] or item['acceptance']['acceptance'] == 'needs_review': continue
        if old is None:
            # Inactive conflicting reservations remain in review, not a misleading new import.
            if item['acceptance']['acceptance'] != 'accepted' and item['record']['status'] != 'cancelled': continue
            row = item['record']
            if rid not in state['offered_versions'] and rid not in state['legacy_exports']:
                added.append(rid)
            versions = state['offered_versions'].setdefault(rid, [])
            digest = record_digest(row)
            if digest not in versions:
                versions.append(digest)
            exports.append(row)
        elif old != item['record'] or (item['acceptance']['acceptance'] == 'not_accepted' and old['status'] != 'cancelled'):
            updated.append(rid)
        else:
            unchanged.append(rid)
    # Updates remain pending proposals until the user handles the existing app row.
    newly_observed_docs = {o['document_id'] for o in batch.get('observations', []) if o['id'] not in previous_observation_ids}
    for d in s['documents']:
        refs = sorted({current_assignments[o['id']] for o in obs.values() if o['document_id'] == d['id']})
        if refs and d['state'] not in ['duplicate', 'irrelevant']:
            if d['state'] == 'needs_review':
                retry = d.get('retry', {})
                extraction_recovered = d['id'] in newly_observed_docs and (d.get('reason') == 'read_without_extraction' or (retry.get('active', True) and retry.get('action') == 'extract'))
                if not extraction_recovered: continue
            run_session.mark_document(s, dict(document_id=d['id'], state='parsed', record_ids=refs))
    state['processing_review'] = dict(record_ids=sorted({r['id'] for r in pending}),
                                    financial_units=sorted({r['financial_unit'] for r in spending['pending']}))
    coverage = dict(format='fotonest.coverage.review', version=1, expected_document_ids=list(docs), documents=[])
    for d in s['documents']:
        entry = {k: d[k] for k in ['id', 'account', 'kind', 'state']}
        if d['state'] in ['needs_read', 'read']:
            entry.update(state='needs_review', reason='unread_source' if d['state'] == 'needs_read' else 'read_without_extraction')
        else:
            for k in ['record_ids', 'reason', 'duplicate_of']:
                if k in d: entry[k] = d[k]
        coverage['documents'].append(entry)
    report = dict(format='fotonest.reconciliation.review', version=1, records=current,
                  delta=dict(added=added, updated=updated, unchanged=unchanged, pending=pending, merge_review=merges,
                             pending_import_ids=[r['id'] for r in exports], legacy_unverified_ids=sorted(legacy_unverified)),
                  acceptance=acceptance, spending=spending, coverage=coverage,
                  coverage_summary=audit_coverage.audit(coverage), processing=run_session.processing_status(s), source_observations=state['observations'],
                  record_links=state['same_record'], amount_observations=state['amounts'],
                  app_modified=False, generated_does_not_mean_imported=True)
    return s, report, exports


def write_outputs(session_path, batch, output_dir, results=None):
    session = run_session.load_session(session_path)
    state, review, records = reconcile(session, batch, results)
    root = Path(output_dir); root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The prior file may contain just-confirmed rows. Withdraw it before publishing.
    run_session.save_session(root / 'latest.json', dict(state='in_progress', import_files=[]))
    # Commit evidence and confirmations before materializing the derived files.
    # A retry can recreate the files from the checkpoint even without a batch.
    run_session.save_session(session_path, state)
    digest = hashlib.sha256(json.dumps(review, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    folder = root / ('run-' + digest); folder.mkdir(mode=0o700, exist_ok=True)
    files = []
    for start in range(0, len(records), 100):
        data = dict(format='fotonest.travel', version=1, records=records[start:start+100])
        validate_import.validate(data)
        path = folder / ('new-%03d.fotonest.json' % (start//100 + 1))
        run_session.save_session(path, data); files.append(str(path.resolve()))
    review_path = folder / 'review.json'; run_session.save_session(review_path, review)
    manifest = dict(state='ready', import_files=files, review_file=str(review_path.resolve()),
                    processing=review['processing'],
                    added=len(review['delta']['added']), ready_to_import=len(records),
                    legacy_unverified=len(review['delta']['legacy_unverified_ids']),
                    updates_for_review=len(review['delta']['updated']), app_modified=False)
    run_session.save_session(root / 'latest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--batch', help='evidence batch; omit to resume the checkpoint')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--import-results', help='local file with user-confirmed saved IDs')
    args = parser.parse_args()
    try:
        batch = (read_json(args.batch, 10 * 1024 * 1024) if args.batch else
                 dict(format='fotonest.evidence.batch', version=1, observations=[]))
        results = read_json(args.import_results, 2 * 1024 * 1024) if args.import_results else None
        result = write_outputs(args.session, batch, args.output_dir, results)
    except ImportError: raise SystemExit('Install jsonschema before reconciliation')
    except Exception: raise SystemExit('INVALID: reconciliation failed; source files and app were not changed')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
