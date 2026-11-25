import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reconcile_evidence as engine
import run_session


def session():
    return dict(format=run_session.FORMAT, version=1, namespace='synthetic-evaluation',
                accounts=['a', 'b'], scope={'window': 'synthetic'}, queries=[],
                profiles={'spending_policy': 'adopt_booking_price_without_contrary_evidence_bill_first',
                          'traveler_scope': 'selected-orders'},
                documents=[dict(id='doc-' + str(i), account='a' if i % 2 else 'b',
                                kind='email_body', source_id='opaque-' + str(i), state='read', has_been_read=True)
                           for i in range(1, 110)], unrelated={'preserve': True})


def observation(key='one', document='doc-1', order='order-one', role='reservation', **extra):
    record = dict(kind='hotel', title='Synthetic Bay Hotel', start='2024-01-02', end='2024-01-04',
                  status=engine.STATUSES[role], evidence={'title': 'Synthetic Bay Hotel', 'start': 'Jan 2, 2024',
                                                        'end': 'Jan 4, 2024', 'status': role})
    record.update(extra.pop('record', {}))
    return dict(id=key, document_id=document, identity_keys=[order], identity_evidence='same provider logical order',
                role=role, record=record, property_key='synthetic-bay', room_count=1, **extra)


def amount(key='quote', refs=None, basis='booking_total', value='100', **extra):
    return dict(id=key, financial_unit='bill-unit', observation_ids=refs or ['one'], amount=value,
                currency='USD', basis=basis, source='doc-1', evidence='Order total ' + value, **extra)


def batch(*observations, amounts=None, links=None):
    return dict(format='fotonest.evidence.batch', version=1, observations=list(observations),
                amounts=amounts or [], same_record=links or [])


def import_results(files=(), legacy_not_saved_ids=()):
    return dict(format='fotonest.import.results', version=1,
                saved=[dict(file=str(path), ids=ids) for path, ids in files],
                legacy_not_saved_ids=list(legacy_not_saved_ids))


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def confirm(self, state, rows):
        path = self.root / 'initial.fotonest.json'
        run_session.save_session(path, dict(format='fotonest.travel', version=1, records=rows))
        return engine.reconcile(state, batch(), import_results([(path, [r['id'] for r in rows])]))

    def test_copy_cross_account_and_rerun(self):
        s = session(); original = copy.deepcopy(s)
        one, two = observation(), observation('copy', 'doc-2')
        state, report, exports = engine.reconcile(s, batch(one, two, amounts=[amount()]))
        self.assertEqual(s, original)
        self.assertEqual(len(exports), 1)
        self.assertEqual(len(report['records'][0]['observation_ids']), 2)
        self.assertEqual(report['spending']['totals_by_currency'], {'USD': '100'})
        next_state, rerun, replay = engine.reconcile(state, batch(one, two, amounts=[amount()]))
        self.assertEqual(replay, exports)
        self.assertEqual(rerun['delta']['pending_import_ids'], [exports[0]['id']])
        self.assertFalse(rerun['delta']['added'])
        self.assertEqual(next_state['unrelated'], original['unrelated'])
        self.assertGreater(rerun['coverage_summary']['needs_review_including_copies'], 0)

    def test_same_property_orders_and_charge_union(self):
        one, two = observation(), observation('two', 'doc-2', 'order-two')
        second_amount = amount('q2', ['two']); second_amount['financial_unit'] = 'bill-unit-two'
        _, report, exports = engine.reconcile(session(), batch(one, two, amounts=[amount(), second_amount]))
        self.assertEqual(len(exports), 2)
        self.assertEqual(report['acceptance']['nights']['by_property'][0]['nights'], 2)
        self.assertEqual(report['spending']['totals_by_currency'], {'USD': '200'})

    def test_fallback_observation_id_cannot_collide_with_business_key(self):
        a = observation(order='same-opaque-text')
        b = observation('same-opaque-text', 'doc-2'); b.pop('identity_keys'); b.pop('identity_evidence')
        _, _, exports = engine.reconcile(session(), batch(a, b))
        self.assertEqual(len({r['id'] for r in exports}), 2)

    def test_later_bill_corrects_dates_without_new_identity_or_double_money(self):
        state, _, first = engine.reconcile(session(), batch(observation(), amounts=[amount()]))
        state, _, _ = self.confirm(state, first)
        bill = observation('bill', 'doc-2', role='stay_evidence', record={'end': '2024-01-05'})
        state, report, exports = engine.reconcile(state, batch(bill, amounts=[amount('total', ['bill'], 'bill_total', '140')]))
        self.assertFalse(exports)
        self.assertEqual(report['delta']['updated'], [first[0]['id']])
        self.assertEqual(report['records'][0]['record']['end'], '2024-01-05')
        self.assertEqual(report['spending']['totals_by_currency'], {'USD': '140'})
        self.assertEqual(len(report['source_observations']), 2)
        _, rerun, _ = engine.reconcile(state, batch())
        self.assertEqual(rerun['delta']['updated'], report['delta']['updated'])

    def test_cross_account_cancellation_preserves_history_and_zero_nights(self):
        state, _, first = engine.reconcile(session(), batch(observation(), amounts=[amount()]))
        state, _, _ = self.confirm(state, first)
        _, report, exports = engine.reconcile(state, batch(observation('cancel', 'doc-2', role='cancellation')))
        self.assertEqual(report['records'][0]['record']['status'], 'cancelled')
        self.assertEqual(report['delta']['updated'], [first[0]['id']])
        self.assertFalse(exports)
        self.assertFalse(report['acceptance']['nights']['by_property'])
        self.assertFalse(report['spending']['recognized'])

    def test_conflict_is_order_independent_and_immutable_ids(self):
        a, b = observation(), observation('other', 'doc-2', record={'end': '2024-01-05'})
        for rows in [(a, b), (b, a)]:
            _, report, exports = engine.reconcile(session(), batch(*rows))
            self.assertFalse(exports)
            self.assertIn('end', report['records'][0]['conflicts'])
        state, _, _ = engine.reconcile(session(), batch(a))
        a['record']['end'] = '2024-01-06'
        with self.assertRaises(ValueError): engine.reconcile(state, batch(a))

    def test_explicit_revision_and_timestamp_not_input_order(self):
        a = observation(event_at='2023-12-01T10:00:00Z', event_at_basis='original_message_date')
        b = observation('new', 'doc-2', record={'end': '2024-01-06'}, event_at='2023-12-02T10:00:00Z', event_at_basis='original_provider_event')
        _, report, _ = engine.reconcile(session(), batch(a, b))
        self.assertEqual(report['records'][0]['record']['end'], '2024-01-06')
        b.pop('event_at'); b.pop('event_at_basis'); b.update(supersedes=['one'], supersedes_evidence='provider changed checkout')
        _, report, _ = engine.reconcile(session(), batch(a, b))
        self.assertEqual(report['records'][0]['record']['end'], '2024-01-06')

    def test_dangling_and_cycle_fail(self):
        a, b = observation(), observation('two', 'doc-2')
        a.update(supersedes=['two'], supersedes_evidence='revision')
        with self.assertRaises(ValueError): engine.reconcile(session(), batch(a))
        b.update(supersedes=['one'], supersedes_evidence='revision')
        with self.assertRaises(ValueError): engine.reconcile(session(), batch(a, b))

    def test_existing_identity_merge_stays_blocked_on_rerun(self):
        a, b = observation(), observation('two', 'doc-2', 'different-order')
        state, _, exports = engine.reconcile(session(), batch(a, b))
        self.assertEqual(len(exports), 2)
        state, _, _ = self.confirm(state, exports)
        state, report, exports = engine.reconcile(state, batch(links=[{'from': 'one', 'to': 'two', 'basis': 'later explicit same order linkage'}]))
        self.assertFalse(exports)
        self.assertEqual(len(report['delta']['merge_review'][0]['previous_ids']), 2)
        _, again, exports = engine.reconcile(state, batch())
        self.assertEqual(again['delta']['merge_review'], report['delta']['merge_review'])
        self.assertFalse(exports)

    def test_processing_ticket_and_independent_segments(self):
        a = observation(role='processing', record={'kind': 'flight', 'title': 'Synthetic flight'})
        state, _, exports = engine.reconcile(session(), batch(a))
        self.assertFalse(exports)
        b = observation('issued', 'doc-2', record={'kind': 'flight', 'title': 'Synthetic flight'})
        c = observation('leg2', 'doc-3', 'order-one-leg-two', record={'kind': 'flight', 'title': 'Second leg'})
        _, report, exports = engine.reconcile(state, batch(b, c, amounts=[amount(refs=['issued', 'leg2'])]))
        self.assertEqual(len(exports), 2)
        self.assertTrue(all(x['status'] == 'reserved' for x in exports))
        self.assertEqual(report['spending']['totals_by_currency'], {'USD': '100'})

    def test_unexported_processing_identities_can_be_linked(self):
        a, b = observation(role='processing'), observation('two', 'doc-2', 'separate-internal-key', role='processing')
        state, _, exports = engine.reconcile(session(), batch(a, b))
        self.assertFalse(exports)
        issued = observation('issued', 'doc-3', supersedes=['one', 'two'], supersedes_evidence='provider confirms a single logical order')
        _, report, exports = engine.reconcile(state, batch(issued))
        self.assertEqual(len(exports), 1)
        self.assertFalse(report['delta']['merge_review'])

    def test_no_badge_date_fabrication(self):
        actual = observation('survey', 'doc-2', role='stay_evidence', record={'start': None})
        _, report, _ = engine.reconcile(session(), batch(observation(), actual))
        candidate = report['records'][0]['badge_candidates'][0]
        self.assertNotIn('start', candidate)
        self.assertEqual(candidate['end'], '2024-01-04')

    def test_rate_original_quantity_mismatch_is_not_multiplied(self):
        a = observation()
        b = observation('stay', 'doc-2', role='stay_evidence'); b['room_count'] = 2
        _, report, _ = engine.reconcile(session(), batch(a, b, amounts=[amount(basis='nightly_rate_per_room', value='50')]))
        self.assertFalse(report['spending']['recognized'])
        self.assertEqual(report['spending']['pending'][0]['reason'], 'rate_quantity_changed_or_unknown')
        _, report, _ = engine.reconcile(session(), batch(a, b, amounts=[amount(basis='nightly_rate_per_room', value='50'), amount('bill', ['stay'], 'bill_total', '180')]))
        self.assertEqual(report['spending']['totals_by_currency'], {'USD': '180'})

    def test_one_message_two_stays_amount_attaches_to_one(self):
        a = observation()
        b = observation('august', 'doc-1', 'august-order', record={'start': '2024-08-01', 'end': '2024-08-02'})
        _, report, exports = engine.reconcile(session(), batch(a, b, amounts=[amount(refs=['august'])]))
        aug = next(r['id'] for r in exports if r['start'] == '2024-08-01')
        self.assertEqual(report['spending']['recognized'][0]['record_ids'], [aug])

    def test_superseded_rate_quantity_does_not_block_current_revision(self):
        a = observation()
        b = observation('revised', 'doc-2', supersedes=['one'], supersedes_evidence='revised stay length', record={'end': '2024-01-05'})
        old = amount(basis='nightly_rate_per_room', value='50')
        new = amount('revised-rate', ['revised'], 'nightly_rate_per_room', '60', supersedes=['quote'])
        _, report, _ = engine.reconcile(session(), batch(a, b, amounts=[old, new]))
        self.assertEqual(report['spending']['totals_by_currency'], {'USD': '180'})

    def test_unsupported_date_range_is_held(self):
        a = observation(record={'kind': 'flight', 'start': '2024-01-03', 'end': '2024-01-02'})
        _, report, exports = engine.reconcile(session(), batch(a))
        self.assertFalse(exports)
        self.assertIn('v1_projection_invalid', report['records'][0]['conflicts'])

    def test_partial_import_and_repeated_receipt_keep_only_unsaved_rows(self):
        path = self.root / 'session.json'
        output = self.root / 'output'
        run_session.save_session(path, session())
        observations = [observation('o-' + str(i), 'doc-' + str(i), 'order-' + str(i)) for i in range(1, 102)]
        manifest = engine.write_outputs(path, batch(*observations), output)
        self.assertEqual(manifest['added'], 101)
        self.assertEqual(len(manifest['import_files']), 2)
        initial_path = Path(manifest['import_files'][0])
        initial = json.loads(initial_path.read_text())['records']
        self.assertEqual(len(initial), 100)
        self.assertEqual(Path(manifest['review_file']).stat().st_mode & 0o777, 0o600)
        result = import_results([(initial_path, [r['id'] for r in initial[:-1]])])
        after = engine.write_outputs(path, batch(), output, result)
        self.assertEqual(after['ready_to_import'], 2)
        self.assertEqual(len(after['import_files']), 1)
        pending = json.loads(Path(after['import_files'][0]).read_text())['records']
        self.assertIn(initial[-1]['id'], [r['id'] for r in pending])
        self.assertFalse({r['id'] for r in initial[:-1]} & {r['id'] for r in pending})
        self.assertEqual(engine.write_outputs(path, batch(), output, result), after)
        self.assertEqual(json.loads((output / 'latest.json').read_text()), after)
        self.assertTrue(initial_path.exists())

    def test_bill_refreshes_unsaved_export_with_same_identity(self):
        state, _, first = engine.reconcile(session(), batch(observation()))
        bill = observation('bill', 'doc-2', role='stay_evidence', record={'end': '2024-01-05'})
        _, review, pending = engine.reconcile(state, batch(bill))
        self.assertEqual([(r['id'], r['end'], r['status']) for r in pending],
                         [(first[0]['id'], '2024-01-05', 'completed')])
        self.assertFalse(review['delta']['updated'])

    def test_legacy_exports_wait_for_verification_and_keep_ids(self):
        old_state, _, rows = engine.reconcile(session(), batch(observation()))
        checkpoint = old_state['reconciliation']
        for field in ['legacy_exports', 'legacy_not_saved_ids', 'confirmed_imports', 'offered_versions']:
            checkpoint.pop(field)
        checkpoint['generated'] = {row['id']: row for row in rows}
        rid = rows[0]['id']
        state, review, exports = engine.reconcile(old_state, batch())
        self.assertEqual(review['delta']['legacy_unverified_ids'], [rid])
        self.assertFalse(exports)
        _, review, exports = self.confirm(state, rows)
        self.assertEqual(review['delta']['unchanged'], [rid])
        self.assertFalse(exports)
        _, review, exports = engine.reconcile(state, batch(), import_results(legacy_not_saved_ids=[rid]))
        self.assertFalse(review['delta']['legacy_unverified_ids'])
        self.assertEqual(exports, rows)

    def test_confirmation_requires_exact_exported_version(self):
        state, _, rows = engine.reconcile(session(), batch(observation()))
        edited = [{**rows[0], 'title': 'Edited title'}]
        with self.assertRaisesRegex(ValueError, 'version was not exported'):
            self.confirm(state, edited)

    def test_late_confirmation_after_pending_identity_merge_preserves_saved_id(self):
        a, b = observation(), observation('two', 'doc-2', 'different-order')
        state, _, rows = engine.reconcile(session(), batch(a, b))
        linked = batch(links=[{'from': 'one', 'to': 'two', 'basis': 'same underlying order'}])
        state, review, pending = engine.reconcile(state, linked)
        self.assertEqual(len(pending), 1)
        self.assertFalse(review['delta']['merge_review'])
        saved = next(r for r in rows if r['id'] != pending[0]['id'])
        _, review, pending = self.confirm(state, [saved])
        self.assertFalse(pending)
        self.assertEqual(review['records'][0]['id'], saved['id'])

    def test_interruption_writing_first_export_can_recreate_pending_export(self):
        path = self.root / 'session.json'
        output = self.root / 'output'
        run_session.save_session(path, session())
        write = run_session.save_session

        def interrupt_export(path, data):
            if Path(path).name.endswith('.fotonest.json'):
                raise OSError('simulated interruption')
            write(path, data)

        with patch.object(run_session, 'save_session', side_effect=interrupt_export):
            with self.assertRaises(OSError):
                engine.write_outputs(path, batch(observation()), output)
        self.assertEqual(json.loads((output / 'latest.json').read_text())['state'], 'in_progress')
        recovered = engine.write_outputs(path, batch(), output)
        self.assertEqual(recovered['ready_to_import'], 1)
        self.assertEqual(recovered['added'], 0)


if __name__ == '__main__': unittest.main()
