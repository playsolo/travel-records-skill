#!/usr/bin/env python3
"""Bounded execution controller for a synchronous, user-configured host adapter.

The adapter owns AI/connector access. Only persisted session changes count as
progress; its prose and exit-0 claims never establish business completion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import run_session

FORMAT = 'fotonest.execution.control'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def milestones(s, request=None):
    """Monotonic facts, excluding timestamps, retry logs and narrative churn."""
    facts = []
    selected_docs = {r['id'] for r in request['documents']} if request is not None else None
    reconciliation = s.get('reconciliation', {})
    selected_observations = {o['id'] for o in reconciliation.get('observations', []) if selected_docs is None or o['document_id'] in selected_docs}
    for d in s['documents']:
        if request is not None and (request['action'] != 'process_documents' or d['id'] not in selected_docs): continue
        facts.append(['discovered', d['id']])
        if d.get('has_been_read'): facts.append(['read', d['id']])
        if d['state'] in run_session.TERMINAL: facts.append(['disposed', d['id'], d['state']])
    for q in s['queries']:
        if request is not None:
            if request['action'] == 'paginate':
                if (q['account'], q['query_id']) != (request['query']['account'], request['query']['query_id']): continue
            elif request['action'] == 'discover':
                missing = {r['year'] for r in request['processing']['unsearched_email_years'] if r['account'] == q['account']}
                if q['account'] not in request['processing']['unsearched_accounts'] and not missing.intersection(q.get('email_years', [])): continue
            else: continue
        for page in q['pages']: facts.append(['page', q['account'], q['query_id'], page])
    for key in ['observations', 'amounts', 'same_record']:
        for item in reconciliation.get(key, []):
            if request is not None:
                if request['action'] != 'process_documents': continue
                if key == 'observations' and item['document_id'] not in selected_docs: continue
                if key == 'amounts' and item['source'] not in selected_docs: continue
                if key == 'same_record' and item['from'] not in selected_observations and item['to'] not in selected_observations: continue
            facts.append([key, item])
    if 'processing_review' in reconciliation and (request is None or request['action'] == 'reconcile'):
        facts.append(['reconciliation_review', reconciliation['processing_review']])
    return {digest(f) for f in facts}


def inventory(s):
    docs = {d['id']: d for d in s['documents']}
    seen_queries = set()
    for q in s['queries']:
        key = (q['account'], q['query_id'])
        if key in seen_queries or not q['pages']: raise ValueError('invalid query inventory')
        seen_queries.add(key)
        if 'email_years' in s['scope'] and ('email_years' not in q or not set(run_session.email_years(q['email_years'])) <= set(run_session.email_years(s['scope']['email_years']))):
            raise ValueError('query outside authorized email years')
        cursor, visited = None, set()
        for page in q['pages']:
            if page['page_token'] != cursor or cursor in visited: raise ValueError('invalid cursor chain')
            visited.add(cursor)
            if any(ref not in docs or docs[ref]['account'] != q['account'] for ref in page['document_ids']):
                raise ValueError('query source missing')
            cursor = page['next_page_token']
        if (cursor is not None and cursor in visited) or q['next_page_token'] != cursor or q['complete'] != (cursor is None): raise ValueError('invalid query cursor')
    return dict(documents={d['id']: digest({k: d.get(k) for k in ['account', 'kind', 'source_id', 'parent_id']}) for d in s['documents']},
                queries={digest([q['account'], q['query_id']]): dict(identity=digest([q['query'], q.get('email_years')]), pages=[digest(p) for p in q['pages']], complete=q['complete']) for q in s['queries']},
                evidence={k: sorted(digest(x) for x in s.get('reconciliation', {}).get(k, [])) for k in ['observations', 'amounts', 'same_record']})


def assert_retained(previous, current):
    for key, value in previous['documents'].items():
        if current['documents'].get(key) != value: raise ValueError('document inventory lost or replaced')
    for key, old in previous['queries'].items():
        new = current['queries'].get(key)
        if new is None or new['identity'] != old['identity'] or new['pages'][:len(old['pages'])] != old['pages'] or (old['complete'] and new != old):
            raise ValueError('query inventory lost or replaced')
    for key, values in previous['evidence'].items():
        if not set(values) <= set(current['evidence'][key]): raise ValueError('evidence history lost or replaced')


def assert_forward(before, after):
    """Reject inventory loss/scope replacement instead of treating it as progress."""
    for key in ['format', 'version', 'namespace', 'accounts', 'scope', 'profiles']:
        if before[key] != after[key]: raise ValueError('session identity or scope changed')
    assert_retained(inventory(before), inventory(after))


def plan(s, batch_size=10):
    inventory(s)
    queue = run_session.next_documents(s, batch_size)
    processing = queue['processing']
    if processing['can_claim_complete']: action = 'complete'
    elif queue['documents']: action = 'process_documents'
    elif processing['unfinished_queries']: action = 'paginate'
    elif processing['unsearched_accounts'] or processing['unsearched_email_years']: action = 'discover'
    elif processing['reconciliation_review_required']: action = 'reconcile'
    else: action = processing['status']
    request = dict(action=action, processing=processing, documents=queue['documents'],
                   blocked_documents=queue['blocked_documents'], review_documents=queue['review_documents'])
    if action == 'paginate':
        first = processing['unfinished_queries'][0]
        request['query'] = next(q for q in s['queries'] if (q['account'], q['query_id']) == (first['account'], first['query_id']))
    return request


def accepts_expansion(previous, current):
    old, new = dict(previous), dict(current)
    before, after = dict(old.pop('scope')), dict(new.pop('scope'))
    old_years, new_years = run_session.email_years(before.pop('email_years')), run_session.email_years(after.pop('email_years'))
    return old == new and before == after and set(old_years) < set(new_years)


def positive(value):
    return type(value) is int and value > 0


def progress_target(request):
    target = dict(action=request['action'], documents=[dict(id=d['id']) for d in request['documents']],
                  processing={k: request['processing'][k] for k in ['unsearched_accounts', 'unsearched_email_years']})
    if 'query' in request: target['query'] = {k: request['query'][k] for k in ['account', 'query_id']}
    return target


def run(session_path, control_path, worker, max_cycles=20, stall_limit=3, batch_size=10, worker_timeout=180, accept_scope_expansion=False):
    """Run authorized batches; a fresh invocation is an explicit new cycle budget.

    worker(request, cycle) must finish synchronously and return an exit code.
    The caller supplies the same live private session, never a stale mirror.
    """
    if not all(positive(v) for v in [max_cycles, stall_limit, batch_size, worker_timeout]):
        raise ValueError('invalid execution limits')
    path, control = Path(session_path).resolve(), Path(control_path).resolve()
    if path == control: raise ValueError('control cannot overwrite session')
    lock = path.with_name(path.name + '.supervisor.lock')
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    keep_lock = False
    try:
        current = run_session.load_session(path)
        request = plan(current, batch_size)
        binding = dict(path=str(path), namespace=current['namespace'], accounts=current['accounts'],
                       scope=current['scope'], profiles=current['profiles'])
        seen = milestones(current)
        if control.exists():
            saved = json.loads(control.read_text())
            if saved.get('format') != FORMAT or type(saved.get('version')) is not int or saved['version'] != 1:
                raise ValueError('invalid control binding')
            if saved.get('session') != binding:
                if not accept_scope_expansion or not accepts_expansion(saved['session'], binding): raise ValueError('scope changed without explicit expansion')
                saved.update(session=binding, no_progress=0)
            if not isinstance(saved.get('seen'), list) or not all(isinstance(x, str) and len(x) == 64 for x in saved['seen']) or type(saved.get('cycles')) is not int or saved['cycles'] < 0 or type(saved.get('no_progress')) is not int or saved['no_progress'] < 0:
                raise ValueError('invalid control checkpoint')
            assert_retained(saved['inventory'], inventory(current))
            if milestones(current, saved.get('progress_target')) - set(saved['seen']): saved['no_progress'] = 0
            seen |= set(saved['seen'])
        else:
            saved = dict(format=FORMAT, version=1, session=binding, cycles=0, no_progress=0)
        for cycle in range(max_cycles + 1):
            request = plan(current, batch_size)
            if request['action'] in ['complete', 'blocked', 'needs_review']:
                outcome = request['action']; break
            if saved['no_progress'] >= stall_limit:
                outcome = 'stalled'; break
            if cycle == max_cycles:
                outcome = 'budget_exhausted'; break
            saved['cycles'] += 1
            saved.update(status='running', seen=sorted(seen), processing=request['processing'], inventory=inventory(current), progress_target=progress_target(request))
            run_session.save_session(control, saved)
            request.update(format='fotonest.execution.batch', version=1, session_path=str(path),
                           batch_size=batch_size, timeout_seconds=worker_timeout, scope=current['scope'], accounts=current['accounts'])
            try:
                code = worker(request, saved['cycles'])
            except subprocess.TimeoutExpired:
                # A timed-out adapter may still have a remote turn/child alive.
                # Fail closed until its owner verifies it stopped and removes lock.
                keep_lock = True
                outcome = 'worker_timeout'; break
            except KeyboardInterrupt:
                keep_lock = True
                outcome = 'interrupted'; break
            except Exception:
                keep_lock = True
                outcome = 'worker_error'; break
            try:
                after = run_session.load_session(path)
                plan(after, batch_size)
                assert_forward(current, after)
            except (OSError, KeyError, TypeError, ValueError):
                outcome = 'checkpoint_error'; break
            now = milestones(after)
            saved['no_progress'] = 0 if milestones(after, request) - seen else saved['no_progress'] + 1
            seen |= now
            current = after
            if type(code) is not int or code != 0:
                outcome = 'worker_error'; break
        saved.update(status=outcome, seen=sorted(seen), processing=run_session.processing_status(current),
                     can_claim_complete=outcome == 'complete', lock_retained=keep_lock, inventory=inventory(current))
        run_session.save_session(control, saved)
        return {k: saved[k] for k in ['status', 'cycles', 'no_progress', 'processing', 'can_claim_complete', 'lock_retained']}
    finally:
        if not keep_lock: lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('plan'); inspect.add_argument('--session', required=True)
    execute = commands.add_parser('run')
    execute.add_argument('--session', required=True); execute.add_argument('--control', required=True)
    execute.add_argument('--worker-command', required=True, help='Private JSON file containing a trusted argv array; never mail-derived')
    execute.add_argument('--accept-scope-expansion', action='store_true', help='Only after user explicitly adds email years to the saved scope')
    for flag, default in [('max-cycles', 20), ('stall-limit', 3), ('batch-size', 10), ('worker-timeout', 180)]:
        execute.add_argument('--' + flag, type=int, default=default)
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            result = plan(run_session.load_session(args.session))
            code = 0
        else:
            argv = json.loads(Path(args.worker_command).read_text())
            if not isinstance(argv, list) or not argv or not all(run_session.nonempty(a) for a in argv):
                raise ValueError('invalid worker command')
            log_dir = Path(args.control).resolve().with_suffix('.logs')
            if log_dir == Path(args.session).resolve(): raise ValueError('invalid log directory')
            log_dir.mkdir(mode=0o700, exist_ok=True)
            def worker(request, cycle):
                fd = os.open(log_dir / ('cycle-%06d.log' % cycle), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as log:
                    return subprocess.run(argv, input=json.dumps(request).encode(), stdout=log,
                                          stderr=subprocess.STDOUT, timeout=args.worker_timeout, check=False).returncode
            result = run(args.session, args.control, worker, args.max_cycles, args.stall_limit, args.batch_size, args.worker_timeout, args.accept_scope_expansion)
            code = 0 if result['can_claim_complete'] else 2 if result['status'] in ['blocked', 'needs_review', 'budget_exhausted'] else 3
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(code)
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit('INVALID: controller operation failed; preserve the session and inspect the private adapter log')


if __name__ == '__main__':
    main()
