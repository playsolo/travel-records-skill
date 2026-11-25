#!/usr/bin/env python3
"""Recognize explicitly linked financial units; never infer identity or write app data."""
import argparse
import datetime
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import tempfile

POLICIES = {'documented_only', 'adopt_booking_price_without_contrary_evidence_bill_first'}
RANK = {'bill_total': 4, 'invoice_total': 4, 'payment_total': 3, 'booking_total': 2, 'nightly_rate_per_room': 1}
OTHER = {'deposit', 'balance', 'refund', 'tax_component', 'loyalty_points', 'unbooked_quote', 'penalty'}
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')
AMOUNT = re.compile(r'^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?$')


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('invalid identifier')
    return value


def _fields(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= obj.keys() or obj.keys() - set(required) - set(optional):
        raise ValueError('invalid fields')


def recognize(data):
    _fields(data, ['format', 'version', 'policy', 'records', 'amounts'])
    if data['format'] != 'fotonest.spending.input' or type(data['version']) is not int or data['version'] != 1 or data['policy'] not in POLICIES:
        raise ValueError('invalid format or policy')
    if not isinstance(data['records'], list) or not isinstance(data['amounts'], list):
        raise ValueError('invalid lists')
    records = {}
    for r in data['records']:
        _fields(r, ['id', 'kind', 'accepted', 'status'], ['start', 'end', 'room_count', 'property_key', 'title'])
        ident = _id(r['id'])
        if ident in records or r['kind'] not in ('hotel', 'flight', 'dining') or type(r['accepted']) is not bool or r['status'] not in ('unknown', 'reserved', 'processing', 'completed', 'cancelled'):
            raise ValueError('invalid record')
        if 'property_key' in r and r['property_key'] is not None:
            _id(r['property_key'])
        if 'title' in r and (not isinstance(r['title'], str) or len(r['title']) > 200):
            raise ValueError('invalid title')
        if 'room_count' in r and r['room_count'] is not None and (type(r['room_count']) is not int or not 1 <= r['room_count'] <= 10000):
            raise ValueError('invalid rooms')
        for field in ('start', 'end'):
            v = r.get(field)
            if v is not None:
                if not isinstance(v, str) or not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', v):
                    raise ValueError('invalid date')
                parts = [int(p) for p in v.split('-')]
                datetime.date(parts[0], parts[1] if len(parts)>1 else 1, parts[2] if len(parts)>2 else 1)
        records[ident] = r
    amounts = {}
    for a in data['amounts']:
        _fields(a, ['id','financial_unit','record_ids','amount','currency','basis','source','evidence'], ['supersedes'])
        ident = _id(a['id']); _id(a['financial_unit']); _id(a['source'])
        if ident in amounts or a['basis'] not in set(RANK) | OTHER:
            raise ValueError('invalid amount')
        if not isinstance(a['record_ids'], list) or not a['record_ids'] or len(set(a['record_ids'])) != len(a['record_ids']) or any(_id(i) not in records for i in a['record_ids']):
            raise ValueError('invalid record links')
        if not isinstance(a['amount'], str) or not AMOUNT.fullmatch(a['amount']):
            raise ValueError('invalid decimal')
        currency = a['currency']
        if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency)):
            raise ValueError('invalid currency')
        if not isinstance(a['evidence'], str) or not a['evidence'].strip() or len(a['evidence']) > 500:
            raise ValueError('invalid evidence')
        supersedes = a.get('supersedes', [])
        if not isinstance(supersedes, list) or len(set(supersedes)) != len(supersedes):
            raise ValueError('invalid supersedes')
        for item in supersedes: _id(item)
        amounts[ident] = a
    for ident, a in amounts.items():
        for prev in a.get('supersedes', []):
            if prev not in amounts or amounts[prev]['financial_unit'] != a['financial_unit']:
                raise ValueError('invalid supersession')
    visited, active = set(), set()
    def visit(i):
        if i in active: raise ValueError('supersession cycle')
        if i in visited: return
        active.add(i)
        for prev in amounts[i].get('supersedes', []): visit(prev)
        active.remove(i); visited.add(i)
    for ident in amounts: visit(ident)
    units = {}
    for a in amounts.values(): units.setdefault(a['financial_unit'], []).append(a)
    recognized, pending, ignored = [], [], []
    for unit, items in sorted(units.items()):
        items = sorted(items, key=lambda a:a['id'])
        # Refunds need an independent decision, even if the original amount is known.
        if any(a['basis']=='refund' for a in items):
            pending.append({'financial_unit':unit,'reason':'refund_requires_review'}); continue
        candidates = [a for a in items if a['basis'] in RANK and (data['policy'] != 'documented_only' or a['basis'] not in ('booking_total','nightly_rate_per_room'))]
        if not candidates:
            ignored.append({'financial_unit':unit,'reason':'no_eligible_total'}); continue
        # All versions must refer to the same consumption allocation.
        allocations = {tuple(sorted(a['record_ids'])) for a in candidates}
        if len(allocations) != 1:
            pending.append({'financial_unit':unit,'reason':'conflicting_record_allocations'}); continue
        ids = list(next(iter(allocations))); eligible = [records[i]['accepted'] and records[i]['status'] != 'cancelled' for i in ids]
        if not any(eligible):
            if any(a['basis'] in ('bill_total','invoice_total') for a in candidates):
                pending.append({'financial_unit':unit,'reason':'bill_for_unaccepted_or_cancelled_record'})
            else: ignored.append({'financial_unit':unit,'reason':'no_accepted_records'})
            continue
        if not all(eligible):
            pending.append({'financial_unit':unit,'reason':'partially_accepted_allocation'});continue
        # Explicit revision supersedes old observations transitively. Preserve all provenance.
        superseded=set()
        def collect(a):
            for prev in a.get('supersedes', []):
                if prev not in superseded:
                    superseded.add(prev);collect(amounts[prev])
        for a in candidates: collect(a)
        current=[a for a in candidates if a['id'] not in superseded]
        if not current:
            pending.append({'financial_unit':unit,'reason':'no_current_amount'});continue
        rank=max(RANK[a['basis']] for a in current); best=[a for a in current if RANK[a['basis']]==rank]
        values={(Decimal(a['amount']),a['currency']) for a in best}
        if len(values)!=1:
            pending.append({'financial_unit':unit,'reason':'conflicting_equal_priority_amounts'});continue
        value,currency=next(iter(values))
        if currency is None:
            pending.append({'financial_unit':unit,'reason':'unknown_currency'});continue
        chosen=best[0]; derivation=None
        if chosen['basis']=='nightly_rate_per_room':
            if len(ids)!=1 or records[ids[0]]['kind']!='hotel':
                pending.append({'financial_unit':unit,'reason':'nightly_rate_requires_one_hotel'});continue
            r=records[ids[0]]; start,end=r.get('start'),r.get('end'); rooms=r.get('room_count')
            if not start or not end or len(start)!=10 or len(end)!=10 or rooms is None:
                pending.append({'financial_unit':unit,'reason':'nightly_rate_quantity_unknown'});continue
            nights=(datetime.date.fromisoformat(end)-datetime.date.fromisoformat(start)).days
            if nights<=0:
                pending.append({'financial_unit':unit,'reason':'invalid_stay_interval'});continue
            derivation={'rate':str(value),'nights':nights,'rooms':rooms};value *= nights*rooms
        row={'financial_unit':unit,'record_ids':ids,'amount':format(value,'f'),'currency':currency,'basis':chosen['basis'],
             'source_refs':[{'id':a['id'],'source':a['source'],'basis':a['basis'],'evidence':a['evidence']} for a in items]}
        if derivation:row['derivation']=derivation
        recognized.append(row)
    totals={}
    for r in recognized:totals[r['currency']]=totals.get(r['currency'],Decimal(0))+Decimal(r['amount'])
    return {'format':'fotonest.spending.recognition','version':1,'policy':data['policy'],'recognized':recognized,'totals_by_currency':{k:format(v,'f') for k,v in sorted(totals.items())},'pending':pending,'ignored':ignored}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input');parser.add_argument('--output');args=parser.parse_args()
    try:
        with open(args.input, encoding='utf-8') as f: result=recognize(json.load(f))
        content=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
        if args.output:
            target=Path(args.output);fd,name=tempfile.mkstemp(prefix='.spending-',dir=target.parent)
            try:
                os.fchmod(fd,0o600)
                with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(content);f.flush();os.fsync(f.fileno())
                os.replace(name,target)
            finally:
                if os.path.exists(name):os.unlink(name)
        else:print(content,end='')
    except (ValueError, KeyError, TypeError, OSError, InvalidOperation, RecursionError):
        raise SystemExit('INVALID: spending input or output')

if __name__=='__main__':main()
