#!/usr/bin/env python3
"""Run a synthetic FotoNest import from first offer to confirmed saves."""

import argparse
import json
from pathlib import Path
import tempfile

import reconcile_evidence
import resolve_stays
import run_session


SOURCES = Path(__file__).resolve().parents[1] / 'tests/fixtures/reconciliation-sources.json'
HOTEL = 'Example Bay Hotel'
START = '2024-02-01'
PLANNED_END = '2024-02-03'
ACTUAL_END = '2024-02-04'


def observation(document_id, order, role, end, status_excerpt):
    return {
        'id': 'observation-' + document_id,
        'document_id': document_id,
        'identity_keys': [order],
        'identity_evidence': 'Explicit synthetic order reference',
        'property_key': 'example-bay',
        'role': role,
        'room_count': 1,
        'record': {
            'kind': 'hotel', 'title': HOTEL, 'status': reconcile_evidence.STATUSES[role],
            'start': START, 'end': end,
            'evidence': {'title': HOTEL, 'status': status_excerpt,
                         'start': 'February 1, 2024', 'end': f'February {int(end[-2:])}, 2024'},
        },
    }


def amount(document_id, order, value, basis):
    return {
        'id': 'amount-' + document_id, 'financial_unit': 'price-' + order,
        'observation_ids': ['observation-' + document_id], 'amount': value,
        'currency': 'USD', 'basis': basis, 'source': document_id,
        'evidence': f'Stated total USD {value}',
    }


def batch(observations=(), amounts=()):
    return {'format': 'fotonest.evidence.batch', 'version': 1,
            'observations': list(observations), 'amounts': list(amounts)}


def register_stage(checkpoint, inventory, number):
    state = run_session.load_session(checkpoint)
    for account in state['accounts']:
        items = [{k: item[k] for k in ['id', 'kind']} | {'source_id': item['id']}
                 for item in inventory if item['account'] == account]
        if items:
            run_session.record_page(state, dict(account=account, query_id=f'demo-stage-{number}',
                                                query='Synthetic fixture inventory', page_token=None,
                                                next_page_token=None, items=items))
    run_session.save_session(checkpoint, state)


def read_report(manifest):
    return json.loads(Path(manifest['review_file']).read_text(encoding='utf-8'))


def imported(manifest, report, observation_id):
    row_id = next(row['id'] for row in report['records'] if observation_id in row['observation_ids'])
    # This fixture has one small import batch. A live receipt may name several files.
    return {'format': 'fotonest.import.results', 'version': 1,
            'saved': [{'file': manifest['import_files'][0], 'ids': [row_id]}]}


def describe(label, manifest, report):
    nights = sum(slot['nights'] for slot in report['acceptance']['nights']['by_traveler_scope'])
    cost = report['spending']['totals_by_currency']['USD']
    print(f"{label} | {len(report['records'])} orders, {nights} nights, USD {cost}, "
          f"{manifest['ready_to_import']} awaiting import, "
          f"{manifest['updates_for_review']} saved-record updates")


def run_demo(root):
    checkpoint = root / 'session.json'
    outputs = root / 'results'
    stages = json.loads(SOURCES.read_text(encoding='utf-8'))['stages']
    run_session.init(checkpoint, dict(namespace='synthetic-demo', accounts=['mailbox-a', 'mailbox-b'],
                                    scope={'category': 'synthetic demo'},
                                    profiles={'stay_policy': resolve_stays.RETAIN_ORDERS_POLICY,
                                              'spending_policy': 'adopt_booking_price_without_contrary_evidence_bill_first',
                                              'traveler_scope': 'demo'}))
    register_stage(checkpoint, stages[0], 1)
    initial = batch([
        observation('source-a', 'demo-a', 'reservation', PLANNED_END, 'Order DEMO-A is confirmed'),
        observation('source-b', 'demo-b', 'reservation', PLANNED_END, 'Independent order DEMO-B is confirmed'),
        observation('source-copy', 'demo-a', 'reservation', PLANNED_END, 'Forwarded confirmation of DEMO-A'),
    ], [
        amount('source-a', 'demo-a', '100.00', 'booking_total'),
        amount('source-b', 'demo-b', '100.00', 'booking_total'),
    ])
    first = reconcile_evidence.write_outputs(checkpoint, initial, outputs)
    first_report = read_report(first)
    describe('1. Two separate bookings and one forward', first, first_report)

    register_stage(checkpoint, stages[1], 2)
    changes = batch([
        observation('source-bill', 'demo-a', 'stay_evidence', ACTUAL_END, 'Final folio for the actual stay'),
        observation('source-cancel', 'demo-b', 'cancellation', PLANNED_END, 'Order DEMO-B has been cancelled'),
    ], [amount('source-bill', 'demo-a', '140.00', 'bill_total')])
    receipt_b = imported(first, first_report, 'observation-source-b')
    second = reconcile_evidence.write_outputs(checkpoint, changes, outputs, receipt_b)
    second_report = read_report(second)
    describe('2. Simulated partial save, final bill and cancellation', second, second_report)

    resumed = reconcile_evidence.write_outputs(checkpoint, batch(), outputs)
    describe('3. Resume with no new evidence', resumed, read_report(resumed))
    receipt_a = imported(second, second_report, 'observation-source-bill')
    finished = reconcile_evidence.write_outputs(checkpoint, batch(), outputs, receipt_a)
    describe('4. Simulated save of the remaining record', finished, read_report(finished))
    print(f'Artifacts: {root}')
    print(f'Latest manifest: {outputs / "latest.json"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='create this directory for demo artifacts')
    args = parser.parse_args()
    if args.output_dir is None:
        root = Path(tempfile.mkdtemp(prefix='fotonest-demo-'))
    else:
        root = args.output_dir.resolve()
        root.mkdir(mode=0o700)
    run_demo(root)


if __name__ == '__main__':
    main()
