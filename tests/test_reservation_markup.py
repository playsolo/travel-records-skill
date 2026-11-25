from email.message import EmailMessage
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_reconciliation import batch, engine, session
import normalize_email
import read_reservation_jsonld as markup


FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'reservations.jsonld'


class ReservationMarkupTests(unittest.TestCase):
    def test_read_standalone_standard_and_gmail_spellings(self):
        raw = subprocess.check_output([sys.executable, markup.__file__, str(FIXTURE)], text=True)
        result = json.loads(raw)
        self.assertEqual(result['warnings'], [])
        hotel, flight, dining = result['reservations']
        self.assertEqual(hotel['fields']['title'], '示例海湾酒店')
        self.assertEqual(hotel['fields']['start'], '2024-02-01T15:00:00+08:00')
        self.assertEqual(hotel['fields']['status'], 'reserved')
        self.assertEqual(hotel['booking_price'], {'amount': '699.90', 'currency': 'CNY', 'basis': 'booking_total'})
        self.assertEqual(flight['reservation_reference'], 'DEMO-FLIGHT')
        self.assertEqual((flight['fields']['origin'], flight['fields']['destination']), ('SFO', 'HND'))
        self.assertEqual(flight['fields']['end'], '2024-02-08T05:00:00+09:00')
        self.assertEqual(dining['fields']['party_size'], 2)
        self.assertEqual(dining['fields']['status'], 'processing')
        self.assertNotIn('Synthetic traveler', raw)
        self.assertNotIn('private-action', raw)

    def test_normalize_keeps_markup_from_html_alternative_and_visible_conflict(self):
        message = EmailMessage()
        message.set_content('退房日期为2024年2月4日。' * 12)
        message.add_alternative('<script type="application/ld+json">' + FIXTURE.read_text() +
                                '</script><p>退房日期为2024年2月4日。</p>', subtype='html')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'message.eml'
            path.write_bytes(message.as_bytes())
            body = normalize_email.normalize(path, 'demo', root / 'mail')['documents'][0]
            self.assertEqual(body['selected_mime'], 'text/plain')
            self.assertIn('2024年2月4日', body['text'])
            self.assertNotIn('DEMO-HOTEL', body['text'])
            hotel = body['structured_reservations'][0]
            self.assertEqual(hotel['mime_part'], '0.1')
            self.assertEqual(hotel['fields']['end'], '2024-02-03T11:00:00+08:00')

    def test_connector_markup_error_does_not_discard_body_or_later_block(self):
        html = ('<script type="application/ld+json">{"broken":</script>'
                '<script type="application/ld+json">' + FIXTURE.read_text() +
                '</script><p>有用的正文。</p>')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'connector.json'
            path.write_text(json.dumps({'payload': {'mime_type': 'text/html', 'body': {'content': html}}}))
            body = normalize_email.normalize(path, 'demo', root / 'mail')['documents'][0]
            self.assertEqual(body['text'], '有用的正文。')
            self.assertEqual(body['structured_reservations'][0]['script_index'], 1)
            self.assertEqual(body['structured_warnings'][0]['code'], 'invalid_or_oversized_jsonld')

    def test_unnamed_jsonld_attachment_remains_a_separate_readable_file(self):
        message = EmailMessage()
        message.set_content('Booking details are attached.')
        message.add_attachment(FIXTURE.read_bytes(), maintype='application', subtype='ld+json')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'message.eml'
            path.write_bytes(message.as_bytes())
            body, attachment = normalize_email.normalize(path, 'demo', root / 'mail')['documents']
            self.assertNotIn('structured_reservations', body)
            local = root / 'mail' / attachment['local_file']
            self.assertEqual(local.suffix, '.jsonld')
            self.assertEqual(len(json.loads(subprocess.check_output([sys.executable, markup.__file__, str(local)]))['reservations']), 3)

    def test_unknown_status_and_nightly_time_do_not_invent_date_or_completion(self):
        data = {'@context': 'https://schema.org', '@type': 'LodgingReservation',
                'reservationStatus': 'Completed', 'checkinTime': '15:00:00', 'checkoutTime': '2024-02-30',
                'totalPrice': '100', 'reservationFor': {'name': 'Demo', '@type': 'Hotel'}}
        candidates, warnings = markup.extract_jsonld(json.dumps(data))
        self.assertFalse(warnings)
        self.assertEqual(candidates[0]['fields'], {'kind': 'hotel', 'title': 'Demo'})
        self.assertNotIn('booking_price', candidates[0])
        data['reservationStatus'] = 'https://schema.org/ReservationCancelled'
        self.assertEqual(markup.extract_jsonld(json.dumps(data))[0][0]['fields']['status'], 'cancelled')

    def test_external_vocabularies_and_remote_refs_are_not_used(self):
        foreign = {'@context': 'https://example.invalid/context', '@type': 'LodgingReservation',
                   'reservationFor': {'name': 'Not a Schema.org reservation'}}
        unresolved = {'@context': 'https://schema.org', '@type': 'LodgingReservation',
                      'reservationFor': {'@id': 'https://example.invalid/hotel'},
                      'reservationStatus': 'https://example.invalid/ReservationConfirmed'}
        rows, warnings = markup.extract_jsonld(json.dumps([foreign, unresolved]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['fields'], {'kind': 'hotel'})
        self.assertFalse(warnings)
        html = '<script type="application/ld+json" src="https://example.invalid/reservation">' + FIXTURE.read_text() + '</script>'
        self.assertEqual(markup.extract_html(html), ([], []))
        html = '<template><script type="application/ld+json">' + FIXTURE.read_text() + '</script></template>'
        self.assertEqual(markup.extract_html(html), ([], []))

    def test_oversized_reservation_list_warns_about_omitted_items(self):
        candidate = {'@context': 'https://schema.org', '@type': 'LodgingReservation',
                     'reservationFor': {'name': 'Example'}}
        rows, warnings = markup.extract_jsonld(json.dumps([candidate] * (markup.MAX_RESERVATIONS + 1)))
        self.assertEqual(len(rows), markup.MAX_RESERVATIONS)
        self.assertEqual(warnings, ['too_many_reservations'])

    def test_reviewed_markup_flows_through_v1_without_upgrading_status(self):
        candidates, _ = markup.extract_jsonld(FIXTURE.read_text())
        candidate = candidates[0]
        fields = candidate['fields']
        # The host maps reviewed fields to the existing evidence contract.
        obs = dict(id='markup-hotel', document_id='doc-1', role='reservation', record=dict(
            kind=fields['kind'], title=fields['title'], status=fields['status'],
            start=fields['start'][:10], end=fields['end'][:10],
            evidence={'title': fields['title'], 'status': 'Schema.org ReservationConfirmed',
                      'start': fields['start'], 'end': fields['end']}))
        amount = dict(id='markup-quote', observation_ids=[obs['id']], financial_unit='synthetic-booking',
                      source='doc-1', evidence='Schema.org totalPrice', **candidate['booking_price'])
        _, review, exports = engine.reconcile(session(), batch(obs, amounts=[amount]))
        self.assertEqual(exports[0]['status'], 'reserved')
        self.assertNotIn('DEMO-HOTEL', json.dumps(exports))
        self.assertEqual(review['spending']['totals_by_currency'], {'CNY': '699.90'})


if __name__ == '__main__':
    unittest.main()
