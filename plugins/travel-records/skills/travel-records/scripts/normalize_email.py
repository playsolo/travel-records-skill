#!/usr/bin/env python3
"""Normalize authorized local mail. No network/model calls; output remains private."""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
from email import policy
from email.parser import BytesParser
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re

from read_reservation_jsonld import extract_html, MAX_RESERVATIONS


def digest(value):
    return hashlib.sha256(value).hexdigest()


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.stack = []
        self.output = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = tag in {"head", "script", "style", "template"} or "hidden" in attrs or attrs.get("aria-hidden") == "true" or bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", attrs.get("style", ""), re.I))
        if tag not in {"meta", "link", "img", "br", "hr", "input", "source", "wbr"}:
            self.stack.append((tag, hidden))
            self.hidden += int(hidden)
        if not self.hidden and tag in {"br", "p", "div", "tr", "td", "th", "li", "table", "h1", "h2"}:
            self.output.append("\n")

    def handle_endtag(self, tag):
        # Tolerate malformed email HTML without making hidden text visible.
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                self.hidden -= sum(int(hidden) for _, hidden in self.stack[index:])
                del self.stack[index:]
                break
        if not self.hidden and tag in {"p", "div", "tr", "td", "th", "li", "table"}:
            self.output.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.output.append(data)


def visible_text(text, mime):
    if mime == "text/html" or re.search(r"<(?:meta|html|div|table|td|tr)\b", text, re.I):
        parser = VisibleHTML()
        parser.feed(text)
        text = "".join(parser.output)
    text = unescape(text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def decode_text(raw, charset=None):
    # UTF-8 is safe only when decoding succeeds; do not repair already-garbled text by guessing.
    choices = list(dict.fromkeys([charset or "utf-8", "utf-8"]))
    for encoding in choices:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            pass
    return raw.decode("utf-8", errors="replace")


def choose_body(alternatives):
    plain = "\n".join(x["text"] for x in alternatives if x["mime"] == "text/plain")
    html_text = "\n".join(x["text"] for x in alternatives if x["mime"] == "text/html")
    boilerplate = bool(re.search(r"SALT.*(?:Invite|Reminder)|^\[LIVE\].*Invite", plain, re.I))
    # Some multipart messages put only browser/opt-out links in the plain part.
    # Tracking URLs can make that footer longer than a real short message.
    plain_without_urls = re.sub(r"https?://\S+", "", plain, flags=re.I)
    footer_only_candidate = bool(re.search(
        r"view\s+(?:(?:this\s+)?(?:e-?mail|message)\s+)?in\s+(?:your\s+)?browser|"
        r"unsubscribe|opt[ -]?out|退订", plain_without_urls, re.I))
    # Remove only recognizable boilerplate, never everything after a link:
    # some senders put unsubscribe controls above the actual transaction.
    plain_core = re.sub(r"\bIf you would prefer to opt[ -]?out\b.*?by clicking (?:the )?link below[.!]?",
                        "", plain_without_urls, flags=re.I | re.S)
    plain_core = re.sub(r"(?im)^\s*view\s+(?:(?:this\s+)?(?:e-?mail|message)\s+)?in\s+(?:your\s+)?browser[.!]?\s*$", "", plain_core)
    plain_core = re.sub(r"(?im)^\s*(?:to opt[ -]?out[^\n]*link below[.!]?|unsubscribe[:.\s]*|退订[:：.\s]*|(?:\(c\)\s*)?\d{4}[-–]\d{4}[^\n]*all rights reserved[.!]?|all rights reserved[.!]?|[^\n]{0,80}proprietary information[.!]?)\s*$", "", plain_core).strip()
    has_transaction = bool(re.search(r"\d|check[ -]?in|check[ -]?out|arrival|departure|confirmed|confirmation|入住|退房|订单|确认", plain_core, re.I))
    # A footer signal alone is not enough: a full plain order must survive even
    # when the HTML alternative is much longer marketing/legal copy.
    richer_html = (footer_only_candidate and len(plain_core) <= 80 and not has_transaction
                   and len(html_text) > 2 * len(plain_without_urls.strip()))
    damaged = plain.count("\ufffd") > 3
    if html_text and (not plain.strip() or boilerplate or richer_html or damaged or (len(plain) < 100 and len(html_text) > 3 * len(plain))):
        return html_text, "text/html"
    return plain or html_text, "text/plain" if plain else "text/html"


def normalize(path, account, output_dir, max_attachment_bytes=25 * 1024 * 1024):
    if Path(path).stat().st_size > 100 * 1024 * 1024:
        raise ValueError("input exceeds 100 MiB")
    raw = Path(path).read_bytes()
    if not raw or len(raw) > 100 * 1024 * 1024:
        raise ValueError("input must be nonempty and at most 100 MiB")
    bodies, attachments = [], []
    structured_reservations, markup_warnings = [], []

    def add_body(content, mime, part_path):
        bodies.append({"mime": mime, "text": visible_text(content, mime)})
        if mime == "text/html":
            reservations, warnings = extract_html(content)
            remaining = MAX_RESERVATIONS - len(structured_reservations)
            if len(reservations) > remaining:
                warnings.append("too_many_reservations")
            structured_reservations.extend({"mime_part": part_path, **item} for item in reservations[:remaining])
            markup_warnings.extend({"mime_part": part_path, "code": code} for code in warnings)

    if Path(path).suffix.lower() == ".json":
        data = json.loads(raw)
        root = data.get("payload", data)
        if not isinstance(root, dict) or "mime_type" not in root:
            raise ValueError("expected one connector MIME tree with mime_type")
        immutable_id = str(data.get("id") or data.get("message_id") or digest(raw))
        subject = next((h.get("value", "") for h in root.get("headers", []) if h.get("name", "").lower() == "subject"), "")

        def visit(part, part_path="0"):
            mime = part.get("mime_type", "application/octet-stream")
            filename = part.get("filename") or ""
            body = part.get("body") or {}
            if filename or mime == "message/rfc822" or (not mime.startswith("multipart/") and mime not in {"text/plain", "text/html"}) or (body.get("attachment_id") and not body.get("content")):
                encoded = body.get("data")
                payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)) if isinstance(encoded, str) else None
                attachments.append({"part": part_path, "filename": filename, "mime": mime, "remote_attachment_id": body.get("attachment_id"), "bytes": payload})
                return
            if part.get("parts"):
                for index, child in enumerate(part["parts"]):
                    visit(child, part_path + "." + str(index))
            elif mime in {"text/plain", "text/html"}:
                content = body.get("content")
                if content is None and body.get("data"):
                    encoded = body["data"]
                    content = decode_text(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
                if isinstance(content, str):
                    add_body(content, mime, part_path)
        visit(root)
    else:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        immutable_id = str(message.get("Message-ID") or digest(raw))
        subject = str(message.get("Subject") or "")

        def visit(part, part_path="0"):
            mime = part.get_content_type()
            filename = part.get_filename() or ""
            if filename or part.get_content_disposition() == "attachment" or mime == "message/rfc822":
                payload = part.get_payload(decode=True)
                if payload is None and mime == "message/rfc822":
                    payload = b"\n".join(x.as_bytes(policy=policy.default) for x in part.get_payload())
                attachments.append({"part": part_path, "filename": filename, "mime": mime, "bytes": payload})
                return
            if part.is_multipart():
                for index, child in enumerate(part.iter_parts()):
                    visit(child, part_path + "." + str(index))
            elif mime in {"text/plain", "text/html"}:
                payload = part.get_payload(decode=True) or b""
                add_body(decode_text(payload, part.get_content_charset()), mime, part_path)
            else:
                attachments.append({"part": part_path, "filename": filename, "mime": mime, "bytes": part.get_payload(decode=True)})
        visit(message)
    source = "mail-sha256:" + digest((account + "|" + immutable_id).encode())
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "message.normalized.json").exists():
        raise ValueError("output already contains a normalized message; choose a new directory")
    os.chmod(output, 0o700)
    docs = []
    for item in attachments:
        payload = item.pop("bytes")
        doc = {"id": "attachment-" + digest((source + "|" + item["part"]).encode())[:24], "source": source, "kind": "attachment", **item}
        if payload is not None and len(payload) <= max_attachment_bytes:
            content_hash = digest(payload)
            if item["mime"] == "application/ld+json":
                extension = ".jsonld"
            else:
                extension = Path(item["filename"]).suffix.lower() or mimetypes.guess_extension(item["mime"]) or ".bin"
            if extension not in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".bmp", ".heic", ".eml", ".txt", ".html", ".htm", ".csv", ".ics", ".jsonld", ".json"}:
                extension = ".bin"
            filename = "attachment-" + content_hash + extension
            target = output / filename
            if target.is_symlink():
                raise ValueError("refusing attachment symlink")
            if target.exists() and digest(target.read_bytes()) != content_hash:
                raise ValueError("existing attachment content mismatch")
            with target.open("wb") as handle:
                os.chmod(target, 0o600)
                handle.write(payload)
            doc.update(content_sha256=content_hash, local_file=filename)
        else:
            doc["requires_read"] = True
            doc["reason"] = "payload not supplied; use authorized connector" if payload is None else "attachment exceeds local size limit"
        docs.append(doc)
    body, chosen = choose_body(bodies)
    body_doc = {"id": "body-" + digest(source.encode())[:24], "source": source, "kind": "email_body", "text": body, "selected_mime": chosen, "alternatives": bodies}
    if structured_reservations:
        body_doc["structured_reservations"] = structured_reservations
    if markup_warnings:
        body_doc["structured_warnings"] = markup_warnings
    if not body.strip() or body.count("\ufffd") > 3:
        body_doc.update(requires_read=True, reason="body empty or decoded text damaged; inspect alternatives or original source")
    result = {"format": "fotonest.source.private", "version": 1, "account": account, "source": source, "subject": subject, "documents": [body_doc] + docs}
    destination = output / "message.normalized.json"
    if destination.exists():
        raise ValueError("output already contains a normalized message; choose a new directory")
    with destination.open("x", encoding="utf-8") as handle:
        os.chmod(destination, 0o600)
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--account", required=True, help="stable opaque mailbox namespace")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        value = normalize(args.input, args.account, args.output_dir)
    except Exception as error:
        raise SystemExit("NORMALIZATION FAILED: " + type(error).__name__)
    print("NORMALIZED:", len(value["documents"]), "private documents; interpretation still required")
