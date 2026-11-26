"""Controller integration with persisted sessions and synchronous fake hosts."""
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_session as session
import supervise_session as supervisor
import reconcile_evidence as engine
from test_reconciliation import observation, batch


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.path = self.root / 'session.json'
        self.control = self.root / 'control.json'
        self.s = session.init(self.path, dict(namespace='supervisor-test', accounts=['a'], scope={}, profiles={}))

    def page(self, ids=('one', 'two'), **extra):
        session.record_page(self.s, dict(account='a', query_id='query', query='authorized',
            page_token=None, next_page_token=None, items=[dict(id=k, source_id=k, kind='email_body') for k in ids], **extra))
        session.save_session(self.path, self.s)

    def run_controller(self, worker, **kwargs):
        return supervisor.run(self.path, self.control, worker, **kwargs)

    def close_one(self, request, cycle):
        s = session.load_session(self.path)
        session.mark_document(s, dict(document_id=request['documents'][0]['id'], state='irrelevant', reason='nontransaction'))
        session.save_session(self.path, s)
        return 0  # A host can end its turn after one item; controller owns next run.

    def test_host_final_output_cannot_end_pending_queue(self):
        self.page()
        result = self.run_controller(self.close_one, batch_size=1)
        self.assertEqual((result['status'], result['cycles']), ('complete', 2))
        self.assertTrue(result['can_claim_complete'])

    def test_full_read_extract_and_reconcile_cycle(self):
        self.page(ids=('one',))
        def worker(request, cycle):
            s = session.load_session(self.path); row = request['documents'][0]
            if row['next_action'] == 'read':
                session.mark_document(s, dict(document_id=row['id'], state='read'))
            else:
                s, _, _ = engine.reconcile(s, batch(observation(document=row['id'])))
            session.save_session(self.path, s)
            return 0
        result = self.run_controller(worker)
        self.assertEqual((result['status'], result['cycles']), ('complete', 2))
        self.assertEqual(session.load_session(self.path)['documents'][0]['state'], 'parsed')

    def test_done_claim_and_timestamp_churn_stall_without_fake_completion(self):
        self.page()
        def worker(request, cycle):
            s = session.load_session(self.path); s['last_report'] = 'done-' + str(cycle)
            session.save_session(self.path, s); return 0
        result = self.run_controller(worker)
        self.assertEqual((result['status'], result['cycles'], result['no_progress']), ('stalled', 3, 3))
        self.assertFalse(result['can_claim_complete'])
        resumed = self.run_controller(self.close_one)
        self.assertEqual(resumed['cycles'], 3)  # Restart cannot erase the stall.

    def test_unrelated_discovery_does_not_hide_extraction_stall(self):
        self.page()
        def worker(request, cycle):
            s = session.load_session(self.path)
            session.record_page(s, dict(account='a', query_id='extra-' + str(cycle), query='authorized',
                page_token=None, next_page_token=None, items=[dict(id='extra-' + str(cycle), source_id='extra-' + str(cycle), kind='email_body')]))
            session.save_session(self.path, s); return 0
        self.assertEqual(self.run_controller(worker)['status'], 'stalled')
        s = session.load_session(self.path)
        session.record_page(s, dict(account='a', query_id='unrelated-external', query='authorized',
            page_token=None, next_page_token=None, items=[]))
        session.save_session(self.path, s)
        self.assertEqual(self.run_controller(self.close_one)['cycles'], 3)

    def test_dispatch_number_is_durable_before_worker_crashes(self):
        self.page()
        def crash(request, cycle):
            (self.root / ('cycle-%06d.log' % cycle)).touch(exist_ok=False)
            raise SystemExit('simulated host process exit')
        with self.assertRaises(SystemExit): self.run_controller(crash)
        self.assertEqual(json.loads(self.control.read_text())['cycles'], 1)
        def recover(request, cycle):
            self.assertGreater(cycle, 1)
            (self.root / ('cycle-%06d.log' % cycle)).touch(exist_ok=False)
            return self.close_one(request, cycle)
        self.assertEqual(self.run_controller(recover)['status'], 'complete')

    def test_budget_resume_and_external_progress_preserve_identity(self):
        self.page()
        result = self.run_controller(self.close_one, max_cycles=1, batch_size=1)
        self.assertEqual(result['status'], 'budget_exhausted')
        resumed = self.run_controller(self.close_one, max_cycles=1, batch_size=1)
        self.assertEqual((resumed['status'], resumed['cycles']), ('complete', 2))
        self.assertEqual(session.load_session(self.path)['namespace'], 'supervisor-test')

    def test_inventory_loss_is_rejected_during_run_and_after_restart(self):
        self.page()
        def drop(request, cycle):
            s = session.load_session(self.path); s['documents'] = []; s['queries'] = []
            session.save_session(self.path, s); return 0
        result = self.run_controller(drop)
        self.assertEqual(result['status'], 'checkpoint_error')
        self.assertFalse(result['can_claim_complete'])
        with self.assertRaises(ValueError): self.run_controller(self.close_one)

    def test_cursor_cannot_be_claimed_complete_without_actual_page(self):
        self.page(ids=())
        self.s['queries'][0].update(complete=False, next_page_token='missing')
        session.save_session(self.path, self.s)
        with self.assertRaises(ValueError): supervisor.plan(session.load_session(self.path))

    def test_manual_review_is_preserved_without_automatic_repeated_calls(self):
        self.page(ids=('one',))
        session.mark_document(self.s, dict(document_id='one', state='needs_review', reason='conflicting dates'))
        session.save_session(self.path, self.s)
        result = self.run_controller(lambda *_: self.fail('must not auto-resolve review'))
        self.assertEqual((result['status'], result['cycles']), ('needs_review', 0))

    def test_worker_error_and_unknown_timeout_do_not_auto_retry(self):
        self.page()
        self.assertEqual(self.run_controller(lambda *_: 1)['status'], 'worker_error')
        def timeout(*_): raise subprocess.TimeoutExpired('host', 1)
        result = self.run_controller(timeout)
        self.assertEqual(result['status'], 'worker_timeout')
        self.assertTrue(result['lock_retained'])
        with self.assertRaises(FileExistsError): self.run_controller(self.close_one)

    def test_process_lock_prevents_two_writers(self):
        self.page()
        self.path.with_name(self.path.name + '.supervisor.lock').touch()
        with self.assertRaises(FileExistsError): self.run_controller(self.close_one)

    def test_user_interrupt_does_not_dispatch_another_batch(self):
        self.page()
        def interrupt(*_): raise KeyboardInterrupt()
        result = self.run_controller(interrupt)
        self.assertEqual((result['status'], result['cycles']), ('interrupted', 1))
        self.assertTrue(result['lock_retained'])

    def test_subprocess_adapter_protocol_and_private_logs(self):
        self.page()
        adapter = self.root / 'adapter.py'
        adapter.write_text("import json,sys\nsys.path.insert(0, " + repr(str(Path(session.__file__).parent)) + ")\nimport run_session as s\nr=json.load(sys.stdin)\nx=s.load_session(r['session_path'])\ns.mark_document(x,dict(document_id=r['documents'][0]['id'],state='irrelevant',reason='nontransaction'))\ns.save_session(r['session_path'],x)\nprint('ALL DONE raw-email-secret')\n")
        command = self.root / 'worker.json'; command.write_text(json.dumps([sys.executable, str(adapter)]))
        result = subprocess.run([sys.executable, str(Path(supervisor.__file__)), 'run', '--session', str(self.path),
            '--control', str(self.control), '--worker-command', str(command)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['cycles'], 2)
        self.assertNotIn('raw-email-secret', result.stdout + result.stderr)
        for p in [self.control, *self.root.glob('control.logs/*.log')]:
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)


if __name__ == '__main__': unittest.main()
