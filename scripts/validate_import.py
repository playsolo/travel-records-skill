#!/usr/bin/env python3
"""Validate an external AI travel export without transmitting or printing its contents."""
import datetime
import json
from pathlib import Path
import sys


def validate(data):
    import jsonschema
    schema = json.loads((Path(__file__).resolve().parents[1] / 'references/travel-import-v1.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(data)
    seen = set()
    for row in data['records']:
        identity = (row['source'], row['id'])
        if identity in seen:
            raise ValueError('Duplicate source/record identity')
        seen.add(identity)
        for key in ['id', 'source', 'title']:
            if not row[key].strip():
                raise ValueError('Empty required field')
        if any(not v.strip() for v in row['evidence'].values()):
            raise ValueError('Empty evidence')
        for key in ['start', 'end']:
            value = row.get(key)
            if value is not None:
                parts = [int(p) for p in value.split('-')]
                if not 1800 <= parts[0] <= 9999:
                    raise ValueError('Year outside supported range')
                datetime.date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
                if key not in row['evidence']:
                    raise ValueError('Date missing evidence')
        if row.get('start') and row.get('end'):
            if len(row['start']) != len(row['end']) or row['end'] < row['start']:
                raise ValueError('Date range invalid or precision differs')
        for key in ['origin', 'destination']:
            if row.get(key) is not None and (row['kind'] != 'flight' or key not in row['evidence']):
                raise ValueError('Airport missing flight context or evidence')
        if row['status'] != 'unknown' and 'status' not in row['evidence']:
            raise ValueError('Status missing evidence')


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: validate_import.py FILE')
    try:
        with Path(sys.argv[1]).open('rb') as handle:
            raw = handle.read(2 * 1024 * 1024 + 1)
        if not raw or len(raw) > 2 * 1024 * 1024:
            raise ValueError('File must be at most 2 MiB')
        data = json.loads(raw)
        validate(data)
    except ImportError:
        raise SystemExit('Install jsonschema to validate this file')
    except Exception as error:
        # Do not echo the invalid object, which may contain personal excerpts.
        raise SystemExit('INVALID: ' + type(error).__name__)
    print('VALID:', len(data['records']), 'records; review required in FotoNest')


if __name__ == '__main__':
    main()
