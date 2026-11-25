import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/run_session.py'
spec=importlib.util.spec_from_file_location('session',SCRIPT); session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)

class SessionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'session.json';self.cfg=dict(namespace='test',accounts=['a','b'],scope={'window':'synthetic'},profiles={});self.s=session.init(self.path,self.cfg)
 def tearDown(self):self.tmp.cleanup()
 def page(self,token=None,next_token=None,items=None,account='a'):
  return dict(account=account,query_id='q',query='reservation',page_token=token,next_page_token=next_token,items=items or [])
 def item(self,id,source=None):return dict(id=id,kind='email_body',source_id=source or id)
 def test_replay_cursor_and_identity(self):
  first=self.page(None,'p2',[self.item('a1')]);session.record_page(self.s,first);session.record_page(self.s,self.page('p2',None,[self.item('a2')]));session.record_page(self.s,first)
  self.assertEqual(len(self.s['documents']),2);self.assertTrue(self.s['queries'][0]['complete']);self.assertIsNone(self.s['queries'][0]['next_page_token'])
  with self.assertRaises(ValueError):session.record_page(self.s,self.page(None,'p2',[self.item('a1','different')]))
  with self.assertRaises(ValueError):session.record_page(self.s,self.page(None,None,[self.item('a1')],account='b'))
 def test_read_is_pending_terminal_and_cycle(self):
  session.record_page(self.s,self.page(items=[self.item('a1'),self.item('a2')]))
  session.mark_document(self.s,dict(document_id='a1',state='read'));self.assertEqual(session.summary(self.s)['pending'],2);self.assertEqual(session.summary(self.s)['parsed'],0)
  session.mark_document(self.s,dict(document_id='a1',state='parsed',record_ids=['r1']))
  with self.assertRaises(ValueError):session.mark_document(self.s,dict(document_id='a1',state='read'))
  session.mark_document(self.s,dict(document_id='a2',state='duplicate',duplicate_of='a1'))
  session.mark_document(self.s,dict(document_id='a1',state='needs_review',reason='reconsider'))
  with self.assertRaises(ValueError):session.mark_document(self.s,dict(document_id='a1',state='duplicate',duplicate_of='a2'))
 def test_atomic_mode_unknown_fields_and_no_overwrite(self):
  self.s['reconciliation']={'records':[{'id':'r1'}]};session.save_session(self.path,self.s);self.assertEqual(session.load_session(self.path)['reconciliation'],self.s['reconciliation']);self.assertEqual(os.stat(self.path).st_mode & 0o777,0o600)
  with self.assertRaises(FileExistsError):session.init(self.path,self.cfg)
  self.assertEqual(session.load_session(self.path)['reconciliation'],self.s['reconciliation'])
 def test_cli_resume_and_redacted_error(self):
  page=Path(self.tmp.name)/'page.json';page.write_text(json.dumps(self.page(items=[self.item('x')])));r=subprocess.run([sys.executable,str(SCRIPT),'record-page','--session',str(self.path),'--page',str(page)],capture_output=True,text=True);self.assertEqual(r.returncode,0)
  r=subprocess.run([sys.executable,str(SCRIPT),'next','--session',str(self.path),'--limit','1'],capture_output=True,text=True);self.assertEqual(json.loads(r.stdout)['documents'][0]['next_action'],'read')
  page.write_text(json.dumps(self.page(account='secret-invalid',items=[])));r=subprocess.run([sys.executable,str(SCRIPT),'record-page','--session',str(self.path),'--page',str(page)],capture_output=True,text=True);self.assertNotEqual(r.returncode,0);self.assertNotIn('secret-invalid',r.stderr)
 def test_failures_do_not_change_persisted_file(self):
  session.record_page(self.s,self.page(items=[self.item('x')]));session.save_session(self.path,self.s);before=self.path.read_bytes()
  with self.assertRaises(ValueError):session.mark_document(self.s,dict(document_id='x',state='parsed',record_ids=[]))
  self.assertEqual(self.path.read_bytes(),before)

if __name__=='__main__':unittest.main()
