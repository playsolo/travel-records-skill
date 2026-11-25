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


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def load_session(path):
    with open(path, encoding='utf-8') as f:
        s = json.load(f)
    if not isinstance(s, dict) or s.get('format') != FORMAT or type(s.get('version')) is not int or s['version'] != 1:
        raise ValueError('invalid session format')
    if not nonempty(s.get('namespace')) or not isinstance(s.get('accounts'), list) or not s['accounts'] or len(set(s['accounts'])) != len(s['accounts']) or not all(nonempty(a) for a in s['accounts']):
        raise ValueError('invalid session accounts')
    if not all(isinstance(s.get(k), dict) for k in ['scope', 'profiles']) or not all(isinstance(s.get(k), list) for k in ['queries', 'documents']):
        raise ValueError('invalid session data')
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
    queries = [q for q in s['queries'] if q['account'] == account and q['query_id'] == qid]
    if len(queries) > 1: raise ValueError('duplicate query')
    q = queries[0] if queries else dict(account=account, query_id=qid, query=page['query'], next_page_token=None, complete=False, pages=[])
    if q['query'] != page['query']: raise ValueError('query mismatch')
    old = next((p for p in q['pages'] if p['page_token'] == token), None)
    # A page's cursor and inventory must remain stable when replayed.
    items = page['items']; ids = [x.get('id') for x in items if isinstance(x, dict)]
    if len(ids) != len(items) or len(set(ids)) != len(ids): raise ValueError('duplicate page item')
    existing = {d['id']: d for d in s['documents']}
    new = []
    for item in items:
        if not nonempty(item.get('id')) or item.get('kind') not in ['email_body','attachment','screenshot','document'] or not nonempty(item.get('source_id')) or (item.get('parent_id') is not None and not nonempty(item['parent_id'])):
            raise ValueError('invalid document')
        ident = dict(id=item['id'], account=account, kind=item['kind'], source_id=item['source_id'], parent_id=item.get('parent_id'))
        d = existing.get(item['id'])
        if d and any(d.get(k) != v for k,v in ident.items()): raise ValueError('document identity conflict')
        if not d: new.append({**ident, 'state':'needs_read', 'has_been_read':False})
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


def summary(s):
    counts = {k:sum(d['state']==k for d in s['documents']) for k in sorted(STATES)}
    return dict(discovered=len(s['documents']), read=sum(bool(d.get('has_been_read')) for d in s['documents']), parsed=counts['parsed'], pending=counts['needs_read']+counts['read']+counts['needs_review'], states=counts, queries_complete=sum(q['complete'] for q in s['queries']), queries_total=len(s['queries']), mailbox_coverage_proven=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    for name,arg in [('init','config'),('record-page','page'),('mark','update'),('next',None),('summary',None)]:
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
            if a.command in ['record-page','mark']:
                with open(getattr(a,'page' if a.command=='record-page' else 'update'),encoding='utf-8') as f: data=json.load(f)
                (record_page if a.command=='record-page' else mark_document)(s,data); save_session(a.session,s); result=summary(s)
            elif a.command=='next':
                if a.limit < 1: raise ValueError('invalid limit')
                result={'documents':[dict(id=d['id'],account=d['account'],kind=d['kind'],state=d['state'],next_action='extract' if d['state']=='read' else 'review' if d['state']=='needs_review' else 'read') for d in s['documents'] if d['state'] in ['needs_read','read','needs_review']][:a.limit]}
            else: result=summary(s)
        print(json.dumps(result,ensure_ascii=False))
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        raise SystemExit('INVALID: session operation failed')

if __name__=='__main__': main()
