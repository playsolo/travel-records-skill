from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_reconciliation import amount, batch, engine, observation, run_session, session
import plan_followups


class FollowupTests(unittest.TestCase):
    def plan(self, state, review, limit=20):
        return plan_followups.plan(state, review, date(2024, 3, 1), limit)

    def test_past_orders_prioritized_without_treating_bookings_as_completed(self):
        survey = observation('survey', 'doc-2', role='stay_evidence', record={'end': None})
        future = observation('future', 'doc-3', 'order-future',
                             record={'start': '2024-04-01', 'end': '2024-04-04'})
        cancelled = observation('cancelled', 'doc-4', 'order-cancelled', role='cancellation')
        other = observation('other', 'doc-5', 'order-other')
        state, review, _ = engine.reconcile(session(), batch(observation(), survey, future, cancelled, other))
        output = self.plan(state, review, limit=1)
        self.assertEqual(output['total'], 2)
        self.assertEqual(output['tasks'][0]['reasons'], ['complete_actual_dates', 'find_final_bill'])
        self.assertNotIn('confirmed', output['tasks'][0])
        self.assertEqual(next(i for i in review['records'] if 'other' in i['observation_ids'])['record']['status'], 'reserved')

    def test_query_resume_attachment_and_no_results_keep_prior_decision(self):
        state, review, _ = engine.reconcile(session(), batch(observation(), amounts=[amount()]))
        task = self.plan(state, review)['tasks'][0]
        query = dict(account='a', query_id=task['query_prefix'] + 'order-bill', query='synthetic exact order')
        run_session.record_page(state, dict(**query, page_token=None, next_page_token='next',
                                            items=[dict(id='match', kind='email_body', source_id='match')]))
        self.assertEqual(self.plan(state, review)['tasks'][0]['pending_document_ids'], ['match'])
        run_session.mark_document(state, dict(document_id='match', state='irrelevant', reason='different synthetic order'))
        self.assertEqual(self.plan(state, review)['tasks'][0]['action'], 'resume_search')
        run_session.record_page(state, dict(**query, page_token='next', next_page_token=None, items=[]))
        self.assertEqual(self.plan(state, review)['tasks'][0]['action'], 'searched')
        self.assertEqual(review['records'][0]['record']['status'], 'reserved')
        self.assertEqual(review['spending']['totals_by_currency'], {'USD': '100'})
        run_session.record_page(state, dict(account='a', query_id='discovered-attachment', query='attachment',
                                            page_token=None, next_page_token=None,
                                            items=[dict(id='pdf', kind='attachment', source_id='pdf', parent_id='match')]))
        self.assertEqual(self.plan(state, review)['tasks'][0]['pending_document_ids'], ['pdf'])

    def test_linked_final_bill_closes_followup_with_same_id_and_replaces_quote(self):
        state, review, first = engine.reconcile(session(), batch(observation(), amounts=[amount()]))
        self.assertIn('find_final_bill', self.plan(state, review)['tasks'][0]['reasons'])
        bill = observation('bill', 'doc-2', role='stay_evidence', record={'end': '2024-01-05'})
        state, review, revised = engine.reconcile(state, batch(bill, amounts=[amount('bill-total', ['bill'], 'bill_total', '140')]))
        self.assertEqual(self.plan(state, review)['tasks'], [])
        self.assertEqual(revised[0]['id'], first[0]['id'])
        self.assertEqual(revised[0]['end'], '2024-01-05')
        self.assertEqual(review['spending']['totals_by_currency'], {'USD': '140'})

    def test_held_conflict_offers_both_date_anchors_and_rejects_old_review(self):
        state, before, _ = engine.reconcile(session(), batch(observation()))
        conflict = observation('other', 'doc-2', record={'end': '2024-01-05'})
        state, review, _ = engine.reconcile(state, batch(conflict))
        task = self.plan(state, review)['tasks'][0]
        self.assertIn('resolve_stay_conflict', task['reasons'])
        self.assertEqual({span['end'] for span in task['stay_dates']}, {'2024-01-04', '2024-01-05'})
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            self.plan(state, before)

    def test_record_link_retains_prior_query_progress_under_either_identity(self):
        copy = observation('copy', 'doc-2', 'unlinked-copy')
        state, review, _ = engine.reconcile(session(), batch(observation(), copy))
        tasks = self.plan(state, review)['tasks']
        for task in tasks:
            run_session.record_page(state, dict(account='a', query_id=task['query_prefix'] + 'order',
                                                query='synthetic search', page_token=None,
                                                next_page_token=None, items=[]))
        link = dict(**{'from': 'one', 'to': 'copy'}, basis='explicit order identity')
        state, review, _ = engine.reconcile(state, batch(links=[link]))
        merged = self.plan(state, review)['tasks'][0]
        self.assertEqual(merged['action'], 'searched')
        self.assertEqual(len(merged['queries']), 2)

    def test_partial_historical_date_remains_a_search_anchor(self):
        year = observation(record={'start': '2014', 'end': '2014'})
        this_month = observation('current', 'doc-2', 'current-order',
                                 record={'start': '2024-03', 'end': '2024-03'})
        state, review, _ = engine.reconcile(session(), batch(year, this_month))
        output = self.plan(state, review)
        self.assertEqual(output['total'], 1)
        task = output['tasks'][0]
        self.assertEqual(task['stay_dates'], [{'start': '2014', 'end': '2014'}])
        self.assertEqual(task['reasons'], ['complete_planned_dates'])

    def test_cli_uses_ready_manifest_and_emits_private_id_without_raw_source(self):
        script = Path(plan_followups.__file__)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            checkpoint = root / 'session.json'
            output = root / 'output'
            run_session.save_session(checkpoint, session())
            engine.write_outputs(checkpoint, batch(observation()), output)
            args = [sys.executable, str(script), '--session', str(checkpoint), '--manifest',
                    str(output / 'latest.json'), '--as-of', '2024-03-01']
            raw = subprocess.check_output(args, text=True)
            self.assertEqual(json.loads(raw)['counts_by_action'], {'start_search': 1})
            self.assertNotIn('opaque-1', raw)
            run_session.save_session(output / 'latest.json', dict(state='in_progress'))
            failed = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(failed.stdout)


if __name__ == '__main__':
    unittest.main()
