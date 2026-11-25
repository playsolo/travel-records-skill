#!/usr/bin/env python3
"""Validate an offline expense review ledger; never writes to FotoNest."""
import json
import pathlib
import sys

from jsonschema import Draft202012Validator


def validate(path):
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("ledger exceeds 10 MiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((pathlib.Path(__file__).resolve().parents[1] /
                         "references/expenses-review.schema.json").read_text())
    Draft202012Validator(schema).validate(data)
    keys = [(row["source"], row["id"]) for row in data["records"]]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate source/id")
    return len(keys)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: validate_expenses.py FILE")
    try:
        count = validate(pathlib.Path(sys.argv[1]))
    except Exception as error:
        raise SystemExit("INVALID: " + type(error).__name__)
    print(f"VALID: {count} monetary observations; review ledger only")
