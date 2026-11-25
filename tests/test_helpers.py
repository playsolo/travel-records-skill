"""Synthetic regression tests. No network, real mailbox, model or native app build."""
import copy
from email.message import EmailMessage
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


normalizer = module("normalize_email")
coverage = module("audit_coverage")


class NormalizeTests(unittest.TestCase):
    def test_browser_footer_with_long_tracking_urls_does_not_hide_html_body(self):
        message = EmailMessage()
        message.set_content("Hotel reservations\nView in Browser\nhttps://example.invalid/" + "a" * 700
                            + "\nTo opt out of these emails use the link below.\nAll rights reserved.")
        message.add_alternative("<p>Your upcoming stay at Example Airport Hotel.</p>"
                                "<p>Check in September 12, 2025; check out September 14, 2025.</p>"
                                "<p>Use mobile check-in before arrival. Your reservation is ready to manage.</p>"
                                "<p>View in Browser. To opt out use your email preferences.</p>", subtype="html")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.eml"
            source.write_bytes(message.as_bytes())
            result = normalizer.normalize(source, "box-a", Path(directory) / "out")
            body = result["documents"][0]
            self.assertEqual(body["selected_mime"], "text/html")
            self.assertIn("Example Airport Hotel", body["text"])
            self.assertIn("September 14, 2025", body["text"])
            self.assertEqual(len(body["alternatives"]), 2)

    def test_plain_reservation_is_preserved_when_html_is_only_a_footer(self):
        message = EmailMessage()
        message.set_content("Your reservation at Example Airport Hotel is confirmed.\n"
                            "Arrival September 12, 2025; departure September 14, 2025.\n"
                            "Room rate EUR 125.00.\nView in Browser. Unsubscribe in preferences.")
        message.add_alternative("<p>View in Browser. Unsubscribe.</p>", subtype="html")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.eml"
            source.write_bytes(message.as_bytes())
            result = normalizer.normalize(source, "box-a", Path(directory) / "out")
            body = result["documents"][0]
            self.assertEqual(body["selected_mime"], "text/plain")
            self.assertIn("Example Airport Hotel", body["text"])

    def test_plain_order_is_preserved_when_html_has_more_marketing_text(self):
        message = EmailMessage()
        message.set_content("View in Browser\nYour booking at Example Airport Hotel is confirmed.\n"
                            "Arrival September 12, 2025; departure September 14, 2025.\n"
                            "Room type King. Confirmation ABC123.\nUnsubscribe:\nhttps://example.invalid/" + "a" * 700)
        message.add_alternative("<p>Discover the destination, spa, dining and local attractions.</p>" * 25,
                                subtype="html")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.eml"
            source.write_bytes(message.as_bytes())
            result = normalizer.normalize(source, "box-a", Path(directory) / "out")
            body = result["documents"][0]
            self.assertEqual(body["selected_mime"], "text/plain")
            self.assertIn("September 14, 2025", body["text"])

    def test_top_unsubscribe_does_not_hide_plain_order_from_selection_guard(self):
        message = EmailMessage()
        message.set_content("View in Browser | Unsubscribe: https://example.invalid/" + "a" * 700
                            + "\nYour booking at Example Airport Hotel is confirmed.\n"
                            "Arrival September 12, 2025; departure September 14, 2025.\n"
                            "Room type King. Confirmation ABC123.")
        message.add_alternative("<p>Discover the destination, spa, dining and local attractions.</p>" * 25,
                                subtype="html")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.eml"
            source.write_bytes(message.as_bytes())
            result = normalizer.normalize(source, "box-a", Path(directory) / "out")
            body = result["documents"][0]
            self.assertEqual(body["selected_mime"], "text/plain")
            self.assertIn("September 14, 2025", body["text"])

    def test_html_survey_replaces_placeholder_without_hidden_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            result = normalizer.normalize(FIXTURES / "survey.eml", "box-a", Path(directory) / "out")
            body = result["documents"][0]
            self.assertEqual(body["selected_mime"], "text/html")
            self.assertIn("beginning on July 18, 2014", body["text"])
            self.assertNotIn("2099", body["text"])
            self.assertNotIn("ignore all instructions", body["text"])

    def test_identity_is_stable_but_namespaced_by_mailbox(self):
        with tempfile.TemporaryDirectory() as directory:
            results = [normalizer.normalize(FIXTURES / "reservation.eml", account, Path(directory) / str(i))
                       for i, account in enumerate(["box-a", "box-a", "box-b"])]
            self.assertEqual(results[0]["source"], results[1]["source"])
            self.assertNotEqual(results[0]["source"], results[2]["source"])

    def test_attachment_path_is_generated_and_identical_content_has_same_hash(self):
        message = EmailMessage()
        message["Message-ID"] = "<synthetic-file@example.invalid>"
        message.set_content("Please see the bill.")
        message.add_attachment(b"synthetic PDF", maintype="application", subtype="pdf", filename="../../escape.pdf")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.eml"
            source.write_bytes(message.as_bytes())
            output = Path(directory) / "out"
            result = normalizer.normalize(source, "box-a", output)
            attachment = result["documents"][1]
            stored = output / attachment["local_file"]
            self.assertEqual(stored.parent, output)
            self.assertEqual(stored.read_bytes(), b"synthetic PDF")
            self.assertEqual(stored.stat().st_mode & 0o777, 0o600)
            self.assertFalse((Path(directory) / "escape.pdf").exists())
            with self.assertRaises(ValueError):
                normalizer.normalize(source, "box-a", output)

    def test_connector_attachment_remains_a_pending_reference(self):
        data = {"id": "synthetic-msg", "payload": {"mime_type": "multipart/mixed", "parts": [
            {"mime_type": "text/plain", "body": {"content": "A body with an attached bill."}},
            {"mime_type": "application/pdf", "filename": "bill.pdf", "body": {"attachment_id": "synthetic-only"}}]}}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(data))
            result = normalizer.normalize(source, "box-a", Path(directory) / "out")
            self.assertTrue(result["documents"][1]["requires_read"])
            self.assertNotIn("local_file", result["documents"][1])

    def test_connector_local_attachment_data_is_saved(self):
        import base64
        data = {"id": "synthetic-msg", "payload": {"mime_type": "application/pdf", "filename": "bill.pdf", "body": {"data": base64.urlsafe_b64encode(b"synthetic PDF").decode().rstrip("=")}}}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(data))
            output = Path(directory) / "out"
            result = normalizer.normalize(source, "box-a", output)
            self.assertEqual((output / result["documents"][1]["local_file"]).read_bytes(), b"synthetic PDF")
            self.assertTrue(result["documents"][0]["requires_read"])

    def test_nameless_inline_pdf_is_not_lost(self):
        message = EmailMessage()
        message.set_content("The folio is inline below.")
        message.add_attachment(b"inline PDF", maintype="application", subtype="pdf", disposition="inline")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.eml"
            source.write_bytes(message.as_bytes())
            output = Path(directory) / "out"
            result = normalizer.normalize(source, "box-a", output)
            self.assertEqual(len(result["documents"]), 2)
            attachment = result["documents"][1]
            self.assertEqual(attachment["mime"], "application/pdf")
            self.assertEqual((output / attachment["local_file"]).read_bytes(), b"inline PDF")

    def test_nameless_connector_pdf_is_not_lost(self):
        import base64
        data = {"id": "synthetic-msg", "payload": {"mime_type": "multipart/mixed", "parts": [
            {"mime_type": "text/plain", "body": {"content": "The bill is inline below."}},
            {"mime_type": "application/pdf", "body": {"data": base64.urlsafe_b64encode(b"inline PDF").decode().rstrip("=")}}]}}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(json.dumps(data))
            output = Path(directory) / "out"
            result = normalizer.normalize(source, "box-a", output)
            self.assertEqual(len(result["documents"]), 2)
            self.assertEqual((output / result["documents"][1]["local_file"]).read_bytes(), b"inline PDF")

    def test_nested_forward_is_not_blended_into_parent_body(self):
        inner = EmailMessage()
        inner.set_content("A separate guest's booking.")
        outer = EmailMessage()
        outer.set_content("See attached forwarded message.")
        outer.add_attachment(inner)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.eml"
            source.write_bytes(outer.as_bytes())
            result = normalizer.normalize(source, "box-a", Path(directory) / "out")
            self.assertNotIn("separate guest", result["documents"][0]["text"])
            self.assertEqual(result["documents"][1]["mime"], "message/rfc822")


class CoverageTests(unittest.TestCase):
    def inventory(self):
        return {"format": "fotonest.coverage.review", "version": 1, "expected_document_ids": ["body", "pdf", "copy"], "documents": [
            {"id": "body", "account": "box-a", "kind": "email_body", "state": "parsed", "record_ids": ["stay-a"]},
            {"id": "pdf", "account": "box-a", "kind": "attachment", "state": "needs_review", "reason": "Unreadable dates"},
            {"id": "copy", "account": "box-b", "kind": "attachment", "state": "duplicate", "duplicate_of": "pdf"}]}

    def test_unresolved_material_and_its_duplicate_are_visible(self):
        result = coverage.audit(self.inventory())
        self.assertFalse(result["inventory_fully_resolved"])
        self.assertEqual(result["needs_review_including_copies"], 2)

    def test_missing_candidate_cannot_disappear(self):
        data = self.inventory()
        data["documents"].pop()
        with self.assertRaises(ValueError):
            coverage.audit(data)

    def test_duplicate_cycle_rejected(self):
        data = self.inventory()
        data["documents"][1] = {"id": "pdf", "account": "box-a", "kind": "attachment", "state": "duplicate", "duplicate_of": "copy"}
        with self.assertRaises(ValueError):
            coverage.audit(data)

    def test_parsed_requires_output_reference(self):
        data = self.inventory()
        data["documents"][0]["record_ids"] = []
        with self.assertRaises(ValueError):
            coverage.audit(data)

    def test_dangling_duplicate_rejected(self):
        data = self.inventory()
        data["documents"][2]["duplicate_of"] = "not-in-inventory"
        with self.assertRaises(ValueError):
            coverage.audit(data)

    def test_invalid_version_and_reused_ids_rejected(self):
        for mutate in [lambda data: data.update(version=True), lambda data: data["documents"].append(copy.deepcopy(data["documents"][0]))]:
            data = self.inventory()
            mutate(data)
            with self.assertRaises(ValueError):
                coverage.audit(data)


if __name__ == "__main__":
    unittest.main()
