#!/usr/bin/env python3
"""Private, connector-independent resumable document inventory. No network calls."""
import argparse
import json
import os
from pathlib import Path
import tempfile

FORMAT = 'fotonest.import.session'
STATES = {'needs_read', 'read', 'parsed', 'duplicate', 'irrelevant', 'needs_review'}
TERMINAL = {'parsed', 'duplicate', 'irrelevant'}
PRIORITIES = {'normal', 'transaction'}
RETRY_ACTIONS = {'read', 'extract', 'review'}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def email_years(value):
    if not isinstance(value, list) or not value or not all(type(y) is int and 1000 <= y <= 9998 for y in value) or len(set(value)) != len(value):
        raise ValueError('invalid email years')
    return sorted(value)


def extend_years(s, update):
    """Explicitly authorized additive mail scope; never reset evidence identity."""
    if not isinstance(update, dict) or set(update) != {'email_years'}:
        raise ValueError('invalid scope expansion')
    years = email_years(update['email_years'])
    old = email_years(s['scope']['email_years'])
    if not set(old) <= set(years): raise ValueError('cannot shrink email scope')
    s['scope']['email_years'] = years


def load_session(path):
    with open(path, encoding='utf-8') as f:
        s = json.load(f)
    if not isinstance(s, dict) or s.get('format') != FORMAT or type(s.get('version')) is not int or s['version'] != 1:
        raise ValueError('invalid session format')
    if not nonempty(s.get('namespace')) or not isinstance(s.get('accounts'), list) or not s['accounts'] or len(set(s['accounts'])) != len(s['accounts']) or not all(nonempty(a) for a in s['accounts']):
        raise ValueError('invalid session accounts')
    if not all(isinstance(s.get(k), dict) for k in ['scope', 'profiles']) or not all(isinstance(s.get(k), list) for k in ['queries', 'documents']):
        raise ValueError('invalid session data')
    if 'email_years' in s['scope']: email_years(s['scope']['email_years'])
    return s


def save_session(path, state):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.fotonest-session-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def init(path, config):
    if not isinstance(config, dict):
        raise ValueError('invalid config')
    state = dict(format=FORMAT, version=1, namespace=config.get('namespace'), profiles=config.get('profiles'), scope=config.get('scope'), accounts=config.get('accounts'), queries=[], documents=[])
    # Atomic exclusive creation; never replace an existing session.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        load_session(path)
    except Exception:
        os.unlink(path)
        raise
    return state


def record_page(s, page):
    if not isinstance(page, dict) or page.get('account') not in s['accounts'] or not nonempty(page.get('query_id')) or not isinstance(page.get('query'), str) or not isinstance(page.get('items'), list) or 'page_token' not in page or 'next_page_token' not in page:
        raise ValueError('invalid page')
    token, nxt = page['page_token'], page['next_page_token']
    if (token is not None and not nonempty(token)) or (nxt is not None and not nonempty(nxt)):
        raise ValueError('invalid token')
    account, qid = page['account'], page['query_id']
    years = email_years(page['email_years']) if 'email_years' in page else None
    authorized_years = s['scope'].get('email_years')
    if authorized_years is not None and (years is None or not set(years) <= set(email_years(authorized_years))):
        raise ValueError('query exceeds or omits email year scope')
    queries = [q for q in s['queries'] if q['account'] == account and q['query_id'] == qid]
    if len(queries) > 1: raise ValueError('duplicate query')
    q = queries[0] if queries else dict(account=account, query_id=qid, query=page['query'], next_page_token=None, complete=False, pages=[])
    if q['query'] != page['query']: raise ValueError('query mismatch')
    if queries and q.get('email_years') != years: raise ValueError('query email scope mismatch')
    if years is not None: q['email_years'] = years
    old = next((p for p in q['pages'] if p['page_token'] == token), None)
    # A page's cursor and inventory must remain stable when replayed.
    items = page['items']; ids = [x.get('id') for x in items if isinstance(x, dict)]
    if len(ids) != len(items) or len(set(ids)) != len(ids): raise ValueError('duplicate page item')
    existing = {d['id']: d for d in s['documents']}
    new = []
    for item in items:
        if not nonempty(item.get('id')) or item.get('kind') not in ['email_body','attachment','screenshot','document'] or not nonempty(item.get('source_id')) or (item.get('parent_id') is not None and not nonempty(item['parent_id'])):
            raise ValueError('invalid document')
        if item.get('priority', 'normal') not in PRIORITIES:
            raise ValueError('invalid priority')
        ident = dict(id=item['id'], account=account, kind=item['kind'], source_id=item['source_id'], parent_id=item.get('parent_id'))
        d = existing.get(item['id'])
        if d and any(d.get(k) != v for k,v in ident.items()): raise ValueError('document identity conflict')
        if d and 'priority' in item and item['priority'] != d.get('priority', 'normal'):
            raise ValueError('priority replay differs')
        if not d: new.append({**ident, 'state':'needs_read', 'has_been_read':False, 'priority':item.get('priority', 'normal')})
    fingerprint = dict(page_token=token, next_page_token=nxt, document_ids=ids)
    if old:
        if old != fingerprint: raise ValueError('page replay differs')
        return
    if q['pages'] and (q['complete'] or token != q['next_page_token']): raise ValueError('unexpected page cursor')
    if not q['pages'] and token is not None: raise ValueError('first page must start at null')
    if nxt == token and nxt is not None: raise ValueError('cursor does not advance')
    if nxt is not None and any(p['page_token'] == nxt for p in q['pages']): raise ValueError('cursor cycle')
    if not queries: s['queries'].append(q)
    q['pages'].append(fingerprint); q['next_page_token'] = nxt; q['complete'] = nxt is None
    s['documents'].extend(new)


def mark_document(s, update):
    if not isinstance(update, dict) or update.get('state') not in STATES or not nonempty(update.get('document_id')): raise ValueError('invalid update')
    docs = {d['id']:d for d in s['documents']}; d = docs.get(update['document_id'])
    if d is None: raise ValueError('unknown document')
    state = update['state']; previous = d['state']
    if previous in TERMINAL and state not in [previous,'needs_review']: raise ValueError('terminal state requires review')
    if state == 'parsed' and (not isinstance(update.get('record_ids'), list) or not update['record_ids'] or not all(nonempty(x) for x in update['record_ids'])): raise ValueError('parsed needs records')
    if state in ['needs_review','irrelevant'] and not nonempty(update.get('reason')): raise ValueError('state needs reason')
    if state == 'duplicate':
        target = update.get('duplicate_of'); seen = {d['id']}
        while True:
            if target not in docs or target in seen: raise ValueError('duplicate target invalid')
            seen.add(target); other = docs[target]
            if other['state'] != 'duplicate': break
            target = other.get('duplicate_of')
    d['state'] = state
    d['has_been_read'] = d.get('has_been_read',False) or state in ['read','parsed']
    for key in ['record_ids','reason','duplicate_of']: d.pop(key,None)
    for key in ['record_ids','reason','duplicate_of']:
        if key in update: d[key] = update[key]
    # Keep failure IDs for checkpoint replay, but an explicit disposition ends
    # that retry episode. A later semantic review must not revive an old read.
    if 'retry' in d: d['retry']['active'] = False


def validate_retry(retry):
    if not isinstance(retry, dict) or retry.get('action') not in RETRY_ACTIONS or type(retry.get('retryable')) is not bool or type(retry.get('active', True)) is not bool or type(retry.get('limit')) is not int or retry['limit'] < 1:
        raise ValueError('invalid retry')
    attempts = retry.get('attempts')
    if not isinstance(attempts, list) or not attempts or not all(isinstance(a, dict) and nonempty(a.get('id')) and nonempty(a.get('reason')) for a in attempts):
        raise ValueError('invalid attempts')
    if len({a['id'] for a in attempts}) != len(attempts):
        raise ValueError('duplicate attempts')
    history = retry.get('history', [])
    if not isinstance(history, list) or any(not isinstance(a, dict) or not nonempty(a.get('id')) or not nonempty(a.get('reason')) or a.get('action') not in RETRY_ACTIONS or type(a.get('limit')) is not int or a['limit'] < 1 or type(a.get('retryable')) is not bool for a in history):
        raise ValueError('invalid failure history')
    if len({a['id'] for a in history}) != len(history):
        raise ValueError('duplicate failure history')


def record_failure(s, failure):
    if not isinstance(failure, dict) or not all(nonempty(failure.get(k)) for k in ['document_id', 'failure_id', 'reason']) or failure.get('action') not in RETRY_ACTIONS:
        raise ValueError('invalid failure')
    limit, retryable = failure.get('max_attempts', 3), failure.get('retryable', True)
    if type(limit) is not int or limit < 1 or type(retryable) is not bool:
        raise ValueError('invalid failure policy')
    doc = next((d for d in s['documents'] if d['id'] == failure['document_id']), None)
    if doc is None: raise ValueError('unknown document')
    old = doc.get('retry')
    history = []
    if old is not None:
        validate_retry(old)
        history = old.get('history', [dict(a, action=old['action'], limit=old['limit'], retryable=old['retryable']) for a in old['attempts']])
        replay = next((a for a in history if a['id'] == failure['failure_id']), None)
        if replay:
            if replay['reason'] != failure['reason'] or (replay['action'], replay['limit'], replay['retryable']) != (failure['action'], limit, retryable):
                raise ValueError('failure replay differs')
            return
    if doc['state'] in TERMINAL: raise ValueError('cannot fail a terminal document')
    attempts = list(old['attempts']) if old and old.get('active', True) and old['action'] == failure['action'] and doc['state'] == 'needs_review' else []
    attempts.append(dict(id=failure['failure_id'], reason=failure['reason']))
    mark_document(s, dict(document_id=doc['id'], state='needs_review', reason=failure['reason']))
    history = history + [dict(id=failure['failure_id'], reason=failure['reason'], action=failure['action'], limit=limit, retryable=retryable)]
    doc['retry'] = dict(action=failure['action'], limit=limit, retryable=retryable, attempts=attempts, active=True, history=history)


def pending_action(doc):
    if doc['state'] == 'needs_read': return 'read'
    if doc['state'] == 'read': return 'extract'
    if doc['state'] != 'needs_review': return None
    retry = doc.get('retry')
    if retry is not None:
        validate_retry(retry)
        if retry.get('active', True):
            return retry['action'] if retry['retryable'] and len(retry['attempts']) < retry['limit'] else None
    return {'unread_source':'read', 'read_without_extraction':'extract'}.get(doc.get('reason'))


def processing_status(s):
    """Completion of registered work, never proof of mailbox recall or field accuracy."""
    docs = s['documents']
    if any(not nonempty(d.get('id')) or d.get('state') not in STATES or d.get('account') not in s['accounts'] for d in docs) or len({d['id'] for d in docs}) != len(docs):
        raise ValueError('invalid document inventory')
    unfinished = []
    searched = set()
    searched_years = set()
    for q in s['queries']:
        if q.get('account') not in s['accounts'] or not nonempty(q.get('query_id')) or type(q.get('complete')) is not bool:
            raise ValueError('invalid query state')
        searched.add(q['account'])
        for year in email_years(q['email_years']) if 'email_years' in q else []:
            searched_years.add((q['account'], year))
        if not q['complete'] or q.get('next_page_token') is not None:
            unfinished.append(dict(account=q['account'], query_id=q['query_id'], next_page_token=q.get('next_page_token')))
    unsearched = [a for a in s['accounts'] if a not in searched]
    missing_years = [dict(account=a, year=y) for a in s['accounts'] for y in email_years(s['scope']['email_years']) if (a, y) not in searched_years] if 'email_years' in s['scope'] else []
    actions = sum(pending_action(d) is not None for d in docs)
    review = [d for d in docs if d['state'] == 'needs_review' and pending_action(d) is None]
    blocked = sum(d.get('retry') is not None and d['retry'].get('active', True) for d in review)
    reconciliation = s.get('reconciliation')
    if reconciliation is not None and not isinstance(reconciliation, dict):
        raise ValueError('invalid reconciliation state')
    recorded_review = reconciliation.get('processing_review') if reconciliation is not None else None
    review_unknown = reconciliation is not None and recorded_review is None
    if recorded_review is not None and (not isinstance(recorded_review, dict) or any(not isinstance(recorded_review.get(k), list) or not all(nonempty(v) for v in recorded_review[k]) for k in ['record_ids', 'financial_units'])):
        raise ValueError('invalid reconciliation review')
    record_reviews = len(recorded_review['record_ids']) if recorded_review is not None else 0
    financial_reviews = len(recorded_review['financial_units']) if recorded_review is not None else 0
    unresolved = len(review) + record_reviews + financial_reviews + int(review_unknown)
    status = ('not_started' if not docs and not s['queries'] else
              'partial' if actions or unfinished or unsearched or missing_years else
              'blocked' if blocked else 'needs_review' if unresolved else 'complete')
    return dict(status=status, can_claim_complete=status == 'complete', remaining_actions=actions,
                unresolved_review=unresolved, unresolved_documents=len(review), blocked_documents=blocked,
                unresolved_records=record_reviews, unresolved_financial_units=financial_reviews,
                reconciliation_review_required=review_unknown,
                unfinished_queries=unfinished, unsearched_accounts=unsearched,
                unsearched_email_years=missing_years,
                scope='registered_queries_and_documents', mailbox_coverage_proven=False)


def next_documents(s, limit):
    if type(limit) is not int or limit < 1: raise ValueError('invalid limit')
    processing = processing_status(s)
    queued, blocked, review = [], [], []
    for index, doc in enumerate(s['documents']):
        if doc['state'] in TERMINAL: continue
        action = pending_action(doc)
        row = dict(id=doc['id'], account=doc['account'], kind=doc['kind'], state=doc['state'])
        if action:
            # Fresh extraction and evidence take precedence over failed-source retries.
            retrying = doc['state'] == 'needs_review' and doc.get('retry') is not None and doc['retry'].get('active', True)
            rank = (4 if retrying else 0 if action == 'extract' else
                    1 if doc['kind'] == 'attachment' else 2 if doc.get('priority') == 'transaction' else 3)
            row['next_action'] = action
            if retrying: row['attempt_count'] = len(doc['retry']['attempts'])
            queued.append((rank, index, row))
        else:
            row['reason'] = doc.get('reason')
            (blocked if doc.get('retry') is not None and doc['retry'].get('active', True) else review).append(row)
    return dict(documents=[row for _, _, row in sorted(queued)[:limit]],
                blocked_documents=blocked[:limit], review_documents=review[:limit], processing=processing)


def summary(s):
    counts = {k:sum(d['state']==k for d in s['documents']) for k in sorted(STATES)}
    return dict(discovered=len(s['documents']), read=sum(bool(d.get('has_been_read')) for d in s['documents']), parsed=counts['parsed'], pending=counts['needs_read']+counts['read']+counts['needs_review'], states=counts, queries_complete=sum(q['complete'] for q in s['queries']), queries_total=len(s['queries']), mailbox_coverage_proven=False, processing=processing_status(s))


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    for name,arg in [('init','config'),('record-page','page'),('mark','update'),('failure','update'),('extend-years','update'),('next',None),('summary',None),('assert-complete',None)]:
        p=sub.add_parser(name); p.add_argument('--session',required=True)
        if arg: p.add_argument('--'+arg,required=True,help='JSON input file')
        if name=='next': p.add_argument('--limit',type=int,default=20)
    a=parser.parse_args()
    try:
        if a.command=='init':
            with open(a.config,encoding='utf-8') as f: config=json.load(f)
            s=init(a.session,config); result=summary(s)
        else:
            s=load_session(a.session)
            if a.command in ['record-page','mark','failure','extend-years']:
                with open(getattr(a,'page' if a.command=='record-page' else 'update'),encoding='utf-8') as f: data=json.load(f)
                session_file = Path(a.session).resolve()
                if a.command == 'extend-years' and session_file.with_name(session_file.name + '.supervisor.lock').exists():
                    raise ValueError('stop the controller before expanding scope')
                {'record-page':record_page, 'mark':mark_document, 'failure':record_failure, 'extend-years':extend_years}[a.command](s,data); save_session(a.session,s); result=summary(s)
            elif a.command=='next':
                result=next_documents(s,a.limit)
            elif a.command=='assert-complete': result=processing_status(s)
            else: result=summary(s)
        print(json.dumps(result,ensure_ascii=False))
        if a.command == 'assert-complete' and not result['can_claim_complete']:
            raise SystemExit(2)
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        raise SystemExit('INVALID: session operation failed')

if __name__=='__main__': main()
