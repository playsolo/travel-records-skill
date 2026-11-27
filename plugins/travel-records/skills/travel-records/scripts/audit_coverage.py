#!/usr/bin/env python3
"""Account for inventoried source documents, not search recall or extraction accuracy."""
import collections
import json
from pathlib import Path
import sys


def identifier(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256


def audit(data):
    if not isinstance(data, dict) or data.get("format") != "fotonest.coverage.review" or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("invalid coverage format/version")
    expected = data.get("expected_document_ids")
    documents = data.get("documents")
    if not isinstance(expected, list) or not isinstance(documents, list) or len(expected) > 50000 or len(documents) > 50000:
        raise ValueError("expected/document inventory must be lists of at most 50000 entries")
    if not all(identifier(x) for x in expected) or len(expected) != len(set(expected)):
        raise ValueError("expected document IDs must be nonempty and unique")
    by_id = {}
    for row in documents:
        if not isinstance(row, dict) or not identifier(row.get("id")) or row["id"] in by_id:
            raise ValueError("invalid or duplicate document ID")
        if not identifier(row.get("account")) or row.get("kind") not in {"email_body", "attachment", "screenshot", "document"}:
            raise ValueError("missing account namespace or invalid document kind")
        state = row.get("state")
        if state not in {"parsed", "duplicate", "irrelevant", "needs_review"}:
            raise ValueError("every candidate requires an explicit disposition")
        if state == "parsed":
            refs = row.get("record_ids")
            if not isinstance(refs, list) or not refs or not all(identifier(x) for x in refs) or len(refs) != len(set(refs)):
                raise ValueError("parsed document requires unique record/evidence references")
        elif state == "duplicate":
            if not identifier(row.get("duplicate_of")) or row["duplicate_of"] == row["id"]:
                raise ValueError("duplicate requires another document ID")
        elif not identifier(row.get("reason")):
            raise ValueError("irrelevant and needs-review documents require a concrete reason")
        by_id[row["id"]] = row
    if set(by_id) != set(expected):
        raise ValueError("inventory differs from expected candidate IDs")
    resolved = {}
    for doc_id in by_id:
        current, path, visited = doc_id, [], set()
        while current not in resolved:
            if current not in by_id:
                raise ValueError("dangling duplicate reference")
            if current in visited:
                raise ValueError("duplicate reference cycle")
            visited.add(current)
            path.append(current)
            row = by_id[current]
            if row["state"] != "duplicate":
                resolved[current] = current
                break
            current = row["duplicate_of"]
        terminal = resolved[current]
        for item in path:
            resolved[item] = terminal
    states = collections.Counter(x["state"] for x in documents)
    unresolved = sum(by_id[resolved[x]]["state"] == "needs_review" for x in by_id)
    return {"inventoried_documents": len(documents), "dispositions": dict(states), "needs_review_including_copies": unresolved,
            "inventory_fully_resolved": unresolved == 0,
            "does_not_prove": "mailbox recall, extraction accuracy, record-reference existence, or app import"}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: audit_coverage.py coverage.json")
    try:
        path = Path(sys.argv[1])
        if path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("inventory exceeds 10 MiB")
        result = audit(json.loads(path.read_text(encoding="utf-8")))
    except Exception as error:
        raise SystemExit("INVALID INVENTORY: " + type(error).__name__)
    print(json.dumps(result, ensure_ascii=False, indent=2))
