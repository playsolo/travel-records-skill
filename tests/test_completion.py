"""Synthetic completion, retry and checkpoint tests. No mailbox or native build."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_session as session
import reconcile_evidence as engine
from test_reconciliation import observation, batch


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'session.json'
        self.s = session.init(self.path, dict(namespace='synthetic', accounts=['a'], scope={}, profiles={}))

    def page(self, items=(), token=None, next_token=None, account='a'):
        session.record_page(self.s, dict(account=account, query_id='q', query='authorized window',
                            page_token=token, next_page_token=next_token, items=list(items)))

    def item(self, key, **extra):
        return dict(id=key, source_id=key, kind='email_body', **extra)

    def gate(self):
        session.save_session(self.path, self.s)
        before = self.path.read_bytes()
        result = subprocess.run([sys.executable, str(Path(session.__file__)), 'assert-complete',
                                 '--session', str(self.path)], capture_output=True, text=True)
        self.assertEqual(before, self.path.read_bytes())
        return result

    def test_empty_and_unsearched_account_cannot_finish(self):
        self.assertEqual(session.processing_status(self.s)['status'], 'not_started')
        self.assertEqual(self.gate().returncode, 2)
        self.s['accounts'].append('b')
        self.page()
        self.assertEqual(session.processing_status(self.s)['unsearched_accounts'], ['b'])
        self.assertEqual(self.gate().returncode, 2)
        self.page(account='b')
        self.assertEqual(self.gate().returncode, 0)

    def test_finished_pagination_is_not_finished_processing(self):
        self.page([self.item('one'), self.item('two')])
        session.mark_document(self.s, dict(document_id='one', state='read'))
        status = session.processing_status(self.s)
        self.assertEqual(status['status'], 'partial')
        self.assertEqual(status['remaining_actions'], 2)
        self.assertEqual(self.gate().returncode, 2)
        session.mark_document(self.s, dict(document_id='one', state='parsed', record_ids=['r']))
        session.mark_document(self.s, dict(document_id='two', state='irrelevant', reason='marketing'))
        self.assertTrue(session.processing_status(self.s)['can_claim_complete'])
        self.assertEqual(self.gate().returncode, 0)

    def test_open_page_blocks_terminal_documents(self):
        self.page([self.item('one')], next_token='p2')
        session.mark_document(self.s, dict(document_id='one', state='irrelevant', reason='marketing'))
        self.assertEqual(self.gate().returncode, 2)
        self.page(token='p2')
        self.assertEqual(self.gate().returncode, 0)

    def test_unread_review_is_actionable_but_manual_review_stays_unresolved(self):
        self.page([self.item('one')])
        session.mark_document(self.s, dict(document_id='one', state='needs_review', reason='unread_source'))
        self.assertEqual(session.next_documents(self.s, 1)['documents'][0]['next_action'], 'read')
        self.assertEqual(session.processing_status(self.s)['status'], 'partial')
        session.mark_document(self.s, dict(document_id='one', state='needs_review', reason='date conflict'))
        self.assertEqual(session.processing_status(self.s)['status'], 'needs_review')
        self.assertFalse(session.next_documents(self.s, 1)['documents'])
        self.assertEqual(len(session.next_documents(self.s, 1)['review_documents']), 1)
        self.assertEqual(self.gate().returncode, 2)

    def test_queue_prioritizes_extraction_attachments_and_transactions(self):
        self.page([self.item('normal'), self.item('transaction', priority='transaction'),
                   dict(id='pdf', source_id='pdf', kind='attachment'), self.item('read')])
        session.mark_document(self.s, dict(document_id='read', state='read'))
        session.save_session(self.path, self.s)
        restored = session.load_session(self.path)
        self.assertEqual([d['id'] for d in session.next_documents(restored, 4)['documents']],
                         ['read', 'pdf', 'transaction', 'normal'])
        self.assertEqual(self.s, restored)

    def test_retry_replay_budget_and_failure_do_not_starve_other_sources(self):
        self.page([self.item('failed'), self.item('other')])
        failure = dict(document_id='failed', failure_id='attempt-1', action='read',
                       reason='transport closed', retryable=True, max_attempts=2)
        session.record_failure(self.s, failure)
        session.record_failure(self.s, failure)
        self.assertEqual(len(self.s['documents'][0]['retry']['attempts']), 1)
        self.assertEqual(session.next_documents(self.s, 1)['documents'][0]['id'], 'other')
        session.record_failure(self.s, dict(failure, failure_id='attempt-2'))
        session.save_session(self.path, self.s)
        self.s = session.load_session(self.path)
        self.assertEqual([d['id'] for d in session.next_documents(self.s, 10)['documents']], ['other'])
        self.assertEqual(len(session.next_documents(self.s, 10)['blocked_documents']), 1)
        session.mark_document(self.s, dict(document_id='other', state='irrelevant', reason='marketing'))
        self.assertEqual(session.processing_status(self.s)['status'], 'blocked')
        self.assertEqual(self.gate().returncode, 2)
        # A later successful explicit recovery can finish without resetting identity.
        session.mark_document(self.s, dict(document_id='failed', state='read'))
        session.record_failure(self.s, failure)  # Replayed old failure cannot undo success.
        self.assertEqual(self.s['documents'][0]['state'], 'read')
        session.mark_document(self.s, dict(document_id='failed', state='parsed', record_ids=['r']))
        self.assertEqual(self.gate().returncode, 0)

    def test_invalid_failure_leaves_state_unchanged(self):
        self.page([self.item('one')])
        before = copy.deepcopy(self.s)
        with self.assertRaises(ValueError):
            session.record_failure(self.s, dict(document_id='one', failure_id='a', action='read',
                                                reason='error', retryable=True, max_attempts=True))
        self.assertEqual(self.s, before)

    def test_recovered_failure_does_not_replace_later_semantic_review(self):
        self.page([self.item('one')])
        failure = dict(document_id='one', failure_id='attempt-1', action='read', reason='transport closed')
        session.record_failure(self.s, failure)
        session.mark_document(self.s, dict(document_id='one', state='read'))
        session.mark_document(self.s, dict(document_id='one', state='needs_review', reason='date conflict'))
        session.record_failure(self.s, failure)
        self.assertEqual(session.processing_status(self.s)['status'], 'needs_review')
        queue = session.next_documents(self.s, 10)
        self.assertFalse(queue['documents'])
        self.assertFalse(queue['blocked_documents'])
        self.assertEqual(queue['review_documents'][0]['reason'], 'date conflict')

    def test_failure_replay_survives_later_operation_and_recovery(self):
        self.page([self.item('one')])
        first = dict(document_id='one', failure_id='read-1', action='read', reason='timeout')
        session.record_failure(self.s, first)
        session.mark_document(self.s, dict(document_id='one', state='read'))
        session.record_failure(self.s, dict(first, failure_id='extract-1', action='extract'))
        session.mark_document(self.s, dict(document_id='one', state='read'))
        session.save_session(self.path, self.s)
        self.s = session.load_session(self.path)
        before = copy.deepcopy(self.s)
        session.record_failure(self.s, first)
        self.assertEqual(self.s, before)
        with self.assertRaises(ValueError):
            session.record_failure(self.s, dict(first, reason='different failure'))
        self.assertEqual(self.s, before)

    def test_partial_exports_remain_ready_without_claiming_completion(self):
        self.page([self.item('doc-1'), self.item('doc-2')])
        session.mark_document(self.s, dict(document_id='doc-1', state='read'))
        session.save_session(self.path, self.s)
        output = Path(self.tmp.name) / 'results'
        first = engine.write_outputs(self.path, batch(observation()), output)
        self.assertEqual(first['state'], 'ready')
        self.assertEqual(first['processing']['status'], 'partial')
        self.assertFalse(first['processing']['can_claim_complete'])
        original = json.loads(Path(first['import_files'][0]).read_text())
        self.s = session.load_session(self.path)
        session.mark_document(self.s, dict(document_id='doc-2', state='irrelevant', reason='marketing'))
        session.save_session(self.path, self.s)
        final = engine.write_outputs(self.path, batch(), output)
        self.assertEqual(final['processing']['status'], 'complete')
        self.assertEqual(json.loads(Path(final['import_files'][0]).read_text()), original)
        self.assertEqual(self.gate().returncode, 0)

    def test_detected_record_conflict_blocks_manifest_and_saved_session(self):
        self.page([self.item('doc-1'), self.item('doc-2')])
        for key in ['doc-1', 'doc-2']:
            session.mark_document(self.s, dict(document_id=key, state='read'))
        session.save_session(self.path, self.s)
        manifest = engine.write_outputs(self.path, batch(observation(),
            observation('two', 'doc-2', record={'end': '2024-01-05'})), Path(self.tmp.name) / 'results')
        self.assertEqual(manifest['ready_to_import'], 0)
        self.assertEqual(manifest['processing']['status'], 'needs_review')
        self.assertEqual(manifest['processing']['unresolved_records'], 1)
        self.s = session.load_session(self.path)
        self.assertEqual(self.gate().returncode, 2)
        # Explicit newer evidence resolves the conflict on the same record identity.
        resolved = observation('three', 'doc-2', supersedes=['two'], supersedes_evidence='corrected original')
        self.s, report, rows = engine.reconcile(self.s, batch(resolved))
        self.assertEqual(report['processing']['status'], 'complete')
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.gate().returncode, 0)

    def test_reconciliation_preserves_manual_review_and_refreshes_legacy_summary(self):
        self.page([self.item('doc-1')])
        self.s, _, _ = engine.reconcile(self.s, batch(observation()))
        self.s['reconciliation'].pop('processing_review')  # Existing v1 checkpoint.
        self.assertTrue(session.processing_status(self.s)['reconciliation_review_required'])
        self.assertEqual(self.gate().returncode, 2)
        self.s, _, _ = engine.reconcile(self.s, batch())
        self.assertEqual(self.gate().returncode, 0)
        session.mark_document(self.s, dict(document_id='doc-1', state='needs_review', reason='traveler unresolved'))
        self.s, report, _ = engine.reconcile(self.s, batch())
        self.assertEqual(report['processing']['status'], 'needs_review')
        self.assertEqual(self.s['documents'][0]['reason'], 'traveler unresolved')
        self.assertEqual(self.gate().returncode, 2)

    def test_failed_extraction_resolves_when_new_observations_arrive(self):
        self.page([self.item('doc-1')])
        session.mark_document(self.s, dict(document_id='doc-1', state='read'))
        session.record_failure(self.s, dict(document_id='doc-1', failure_id='extract-1',
                                           action='extract', reason='interrupted'))
        self.s, report, _ = engine.reconcile(self.s, batch())
        self.assertEqual(report['processing']['status'], 'partial')
        self.s, report, _ = engine.reconcile(self.s, batch(observation()))
        self.assertEqual(report['processing']['status'], 'complete')
        self.assertEqual(self.gate().returncode, 0)
        session.mark_document(self.s, dict(document_id='doc-1', state='needs_review', reason='missing fields'))
        session.record_failure(self.s, dict(document_id='doc-1', failure_id='extract-2',
                                           action='extract', reason='ocr unavailable', retryable=False))
        self.s, report, _ = engine.reconcile(self.s, batch(observation()))
        self.assertEqual(report['processing']['status'], 'blocked')
        self.assertEqual(self.gate().returncode, 2)


if __name__ == '__main__':
    unittest.main()
