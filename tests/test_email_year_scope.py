import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_session as session
import supervise_session as supervisor
import reconcile_evidence as engine
from test_reconciliation import observation, batch


class EmailYearScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'session.json'; self.control = Path(self.tmp.name) / 'control.json'
        self.s = session.init(self.path, dict(namespace='annual', accounts=['a'], scope={'email_years':[2026]}, profiles={}))

    def page(self, years, qid='q', items=()):
        session.record_page(self.s, dict(account='a', query_id=qid, query='bounded mail query', email_years=years,
            page_token=None, next_page_token=None, items=list(items)))

    def test_annual_query_cannot_omit_or_expand_year_scope(self):
        before = copy.deepcopy(self.s)
        for years in [[2025], [2025,2026], [], [True]]:
            with self.assertRaises(ValueError): self.page(years)
            self.assertEqual(self.s, before)
        with self.assertRaises(ValueError):
            session.record_page(self.s, dict(account='a', query_id='missing', query='query', page_token=None, next_page_token=None, items=[]))
        self.assertEqual(supervisor.plan(self.s)['action'], 'discover')
        self.page([2026]); self.assertTrue(session.processing_status(self.s)['can_claim_complete'])

    def test_scope_expansion_reopens_discovery_and_retains_record_identity(self):
        self.page([2026], items=[dict(id='doc-1', source_id='one', kind='email_body')])
        self.s, _, old_rows = engine.reconcile(self.s, batch(observation(record={'start':'2026-03-01','end':'2026-03-03'})))
        session.extend_years(self.s, {'email_years':[2025,2026]})
        self.assertEqual(session.processing_status(self.s)['unsearched_email_years'], [dict(account='a',year=2025)])
        self.assertEqual(supervisor.plan(self.s)['action'], 'discover')
        self.page([2025], 'new-year', [dict(id='doc-2', source_id='two', kind='email_body')])
        self.s, _, revised = engine.reconcile(self.s, batch(observation('bill','doc-2',role='stay_evidence',record={'start':'2026-03-01','end':'2026-03-04'})))
        self.assertEqual(old_rows[0]['id'], revised[0]['id'])
        self.assertEqual(revised[0]['end'], '2026-03-04')
        self.assertEqual(self.s['namespace'], 'annual')
        with self.assertRaises(ValueError): session.extend_years(self.s, {'email_years':[2026]})

    def test_controller_requires_explicit_additive_expansion(self):
        self.page([2026]); session.save_session(self.path,self.s)
        supervisor.run(self.path,self.control,lambda *_:0)
        session.extend_years(self.s, {'email_years':[2025,2026]}); session.save_session(self.path,self.s)
        with self.assertRaises(ValueError): supervisor.run(self.path,self.control,lambda *_:0)
        def worker(request, cycle):
            self.assertEqual(request['action'],'discover')
            self.page([2025],'added'); session.save_session(self.path,self.s); return 0
        result=supervisor.run(self.path,self.control,worker,accept_scope_expansion=True)
        self.assertEqual(result['status'],'complete')

    def test_searching_an_already_covered_year_cannot_hide_missing_year_stall(self):
        session.extend_years(self.s, {'email_years':[2025,2026]})
        self.page([2026]);session.save_session(self.path,self.s)
        def wrong_year(request, cycle):
            self.s=session.load_session(self.path)
            self.page([2026],'wrong-year-'+str(cycle))
            session.save_session(self.path,self.s);return 0
        result=supervisor.run(self.path,self.control,wrong_year,max_cycles=5,stall_limit=2)
        self.assertEqual((result['status'],result['cycles'],result['no_progress']),('stalled',2,2))


if __name__ == '__main__': unittest.main()
