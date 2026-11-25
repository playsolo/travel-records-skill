import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/recognize_spending.py'
spec=importlib.util.spec_from_file_location('recognize_spending',SCRIPT);engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

def record(id='r', **kw):
 return {'id':id,'kind':'hotel','accepted':True,'status':'reserved','start':'2024-01-01','end':'2024-01-03','room_count':2,**kw}
def amount(id='a',unit='u',basis='booking_total',value='100.00',currency='USD',ids=None,**kw):
 return {'id':id,'financial_unit':unit,'record_ids':ids or ['r'],'amount':value,'currency':currency,'basis':basis,'source':'mail:one','evidence':'stated amount',**kw}
def data(rs=None,am=None,policy='adopt_booking_price_without_contrary_evidence_bill_first'):
 return {'format':'fotonest.spending.input','version':1,'policy':policy,'records':rs or [record()],'amounts':am if am is not None else [amount()]}

class SpendingTests(unittest.TestCase):
 def test_quote_bill_and_components_count_once(self):
  d=data(am=[amount(),amount('b',basis='bill_total',value='120.00'),amount('p',basis='payment_total',value='120.00'),amount('tax',basis='tax_component',value='20.00')]);original=copy.deepcopy(d);out=engine.recognize(d)
  self.assertEqual(out['totals_by_currency'],{'USD':'120.00'});self.assertEqual(out['recognized'][0]['basis'],'bill_total');self.assertEqual(d,original)
 def test_same_price_independent_orders(self):
  out=engine.recognize(data([record('r'),record('s')],[amount(),amount('b','v',ids=['s'])]));self.assertEqual(out['totals_by_currency'],{'USD':'200.00'});self.assertEqual(len(out['recognized']),2)
 def test_policy_and_unknown_currency(self):
  self.assertFalse(engine.recognize(data(policy='documented_only'))['recognized']);self.assertEqual(engine.recognize(data(am=[amount(currency=None)]))['pending'][0]['reason'],'unknown_currency')
 def test_different_currency_bill_replaces_quote_no_fx(self):
  out=engine.recognize(data(am=[amount(),amount('b',basis='bill_total',value='500',currency='THB')]));self.assertEqual(out['totals_by_currency'],{'THB':'500'})
 def test_conflict_and_explicit_revision(self):
  a=amount();b=amount('b',value='110');self.assertTrue(engine.recognize(data(am=[a,b]))['pending']);b['supersedes']=['a'];self.assertEqual(engine.recognize(data(am=[a,b]))['totals_by_currency'],{'USD':'110'})
 def test_nightly_rate_two_rooms_and_missing_quantity(self):
  out=engine.recognize(data(am=[amount(basis='nightly_rate_per_room',value='50')]));self.assertEqual(out['totals_by_currency'],{'USD':'200'});self.assertEqual(out['recognized'][0]['derivation']['nights'],2)
  self.assertTrue(engine.recognize(data([record(room_count=None)],[amount(basis='nightly_rate_per_room')]))['pending'])
 def test_multi_segment_and_partial_cancel(self):
  rs=[record('r',kind='flight'),record('s',kind='flight')];a=amount(ids=['r','s']);self.assertEqual(engine.recognize(data(rs,[a]))['totals_by_currency'],{'USD':'100.00'});rs[1]['status']='cancelled';self.assertTrue(engine.recognize(data(rs,[a]))['pending'])
 def test_canceled_quote_ignored_but_bill_pending(self):
  rs=[record(status='cancelled')];self.assertTrue(engine.recognize(data(rs,[amount()]))['ignored']);self.assertEqual(engine.recognize(data(rs,[amount(basis='bill_total')]))['pending'][0]['reason'],'bill_for_unaccepted_or_cancelled_record')
 def test_refund_never_silently_deducted(self):
  self.assertEqual(engine.recognize(data(am=[amount(),amount('refund',basis='refund',value='10')]))['pending'][0]['reason'],'refund_requires_review')
 def test_invalid_and_cycles(self):
  for v in ['NaN','-1','1e9','0.1234567']:
   with self.subTest(v=v),self.assertRaises(ValueError):engine.recognize(data(am=[amount(value=v)]))
  with self.assertRaises(ValueError):engine.recognize(data(am=[amount(supersedes=['b']),amount('b',supersedes=['a'])]))
  with self.assertRaises(ValueError):engine.recognize(data(am=[amount(supersedes=['b']),amount('b','other')]))
 def test_stable_order_and_atomic_private_output(self):
  d=data([record('r'),record('s')],[amount('b','v',ids=['s']),amount()]);v=engine.recognize(d);d['amounts'].reverse();self.assertEqual(v,engine.recognize(d))
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);(p/'input').write_text(json.dumps(d));subprocess.run([sys.executable,str(SCRIPT),str(p/'input'),'--output',str(p/'result')],check=True);self.assertEqual((p/'result').stat().st_mode&0o777,0o600);self.assertEqual(json.loads((p/'result').read_text()),v)

if __name__=='__main__': unittest.main()
