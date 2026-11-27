#!/usr/bin/env python3
"""Read compact Schema.org reservation markup as private evidence candidates."""

import argparse
from datetime import date, datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re


MAX_INPUT = 2 * 1024 * 1024
MAX_BLOCK = 256 * 1024
MAX_BLOCKS = 32
MAX_GRAPH_NODES = 1024
MAX_RESERVATIONS = 200
SCHEMA_NAMESPACES = ('https://schema.org', 'http://schema.org')
KINDS = {
    'LodgingReservation': 'hotel',
    'FlightReservation': 'flight',
    'FoodEstablishmentReservation': 'dining',
}
STATUSES = {
    'ReservationConfirmed': 'reserved', 'Confirmed': 'reserved',
    'ReservationCancelled': 'cancelled', 'Cancelled': 'cancelled',
    'ReservationPending': 'processing', 'Pending': 'processing',
    'ReservationHold': 'processing', 'Hold': 'processing',
}


def schema_term(value):
    if isinstance(value, dict) and set(value) == {'@id'}:
        value = value['@id']
    if not isinstance(value, str):
        return None
    for namespace in SCHEMA_NAMESPACES:
        prefix = namespace + '/'
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def schema_context(value):
    return isinstance(value, str) and value.rstrip('/') in SCHEMA_NAMESPACES


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate JSON key')
        obj[key] = value
    return obj


def invalid_constant(_):
    raise ValueError('non-JSON number')


def graph_nodes(data):
    # Visit explicit graph containers; arbitrary nested vendor fields are not graphs.
    todo = [(data, '$', False, 0)]
    nodes = []
    visited = 0
    while todo:
        value, path, context, depth = todo.pop()
        visited += 1
        if depth > 12 or visited > MAX_GRAPH_NODES:
            raise ValueError('graph too large')
        if isinstance(value, list):
            if len(value) + visited + len(todo) > MAX_GRAPH_NODES:
                raise ValueError('graph too large')
            todo.extend((item, f'{path}[{index}]', context, depth + 1)
                        for index, item in reversed(list(enumerate(value))))
        elif isinstance(value, dict):
            if '@context' in value:
                context = schema_context(value['@context'])
            if context:
                nodes.append((value, path))
            if '@graph' in value:
                todo.append((value['@graph'], f'{path}.@graph', context, depth + 1))
    return nodes


def types(node):
    value = node.get('@type')
    values = value if isinstance(value, list) else [value]
    return {schema_term(term) for term in values}


def linked_object(value, indexed):
    if not isinstance(value, dict):
        return {}
    if '@context' in value and not schema_context(value['@context']):
        return {}
    if set(value) == {'@id'} and isinstance(value['@id'], str):
        return indexed.get(value['@id'], {})
    return value


def short_text(value, limit=200):
    if isinstance(value, str):
        value = value.strip()
        if 0 < len(value) <= limit and value.isprintable():
            return value
    return None


def date_time(value):
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            date.fromisoformat(value)
        elif re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?', value):
            datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            return None
    except ValueError:
        return None
    # Retain the offset and sender's local day for interpretation.
    return value


def full_airport(value, indexed):
    code = linked_object(value, indexed).get('iataCode')
    return code if isinstance(code, str) and re.fullmatch(r'[A-Z]{3}', code) else None


def booking_price(node, indexed):
    amount = node.get('totalPrice')
    currency = node.get('priceCurrency')
    if isinstance(amount, dict):
        spec = linked_object(amount, indexed)
        if 'PriceSpecification' not in types(spec):
            return None
        own_currency = spec.get('priceCurrency')
        if currency is not None and own_currency is not None and currency != own_currency:
            return None
        currency = own_currency or currency
        amount = spec.get('price')
    if type(amount) is int:
        amount = str(amount)
    if not isinstance(amount, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?', amount):
        return None
    if not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency):
        return None
    return {'amount': amount, 'currency': currency, 'basis': 'booking_total'}


def reservation(node, path, reservation_type, indexed):
    kind = KINDS[reservation_type]
    item = linked_object(node.get('reservationFor'), indexed)
    fields = {'kind': kind}
    status = STATUSES.get(schema_term(node.get('reservationStatus')))
    if status:
        fields['status'] = status

    if kind == 'flight':
        number = item.get('flightNumber')
        flight_number = short_text(str(number) if type(number) is int else number, 16)
        airline = short_text(linked_object(item.get('airline'), indexed).get('name'), 100)
        fields.update(airline=airline, flight_number=flight_number,
                      origin=full_airport(item.get('departureAirport'), indexed),
                      destination=full_airport(item.get('arrivalAirport'), indexed),
                      start=date_time(item.get('departureTime')), end=date_time(item.get('arrivalTime')))
    else:
        fields['title'] = short_text(item.get('name'))
        if kind == 'hotel':
            fields.update(start=date_time(node.get('checkinTime')), end=date_time(node.get('checkoutTime')))
        else:
            fields.update(start=date_time(node.get('startTime')), end=date_time(node.get('endTime')))
            party = node.get('partySize')
            if isinstance(party, dict):
                party = linked_object(party, indexed).get('value')
            if isinstance(party, str) and re.fullmatch(r'[0-9]{1,4}', party):
                party = int(party)
            if type(party) is int and 1 <= party <= 10000:
                fields['party_size'] = party

    # Only keep fields used in the private review. Personal and action fields stay in the source.
    result = {'path': path, 'type': reservation_type,
              'fields': {key: value for key, value in fields.items() if value is not None}}
    references = {node[key] for key in ('reservationId', 'reservationNumber') if
                  isinstance(node.get(key), str) and re.fullmatch(r'[A-Za-z0-9._-]{1,128}', node[key])}
    if len(references) == 1:
        result['reservation_reference'] = references.pop()
    price = booking_price(node, indexed)
    if price:
        result['booking_price'] = price
    return result


def extract_jsonld(text):
    try:
        if len(text.encode('utf-8')) > MAX_BLOCK:
            return [], ['jsonld_block_too_large']
        data = json.loads(text, object_pairs_hook=unique_keys, parse_float=str, parse_constant=invalid_constant)
        nodes = graph_nodes(data)
    except (ValueError, RecursionError):
        return [], ['invalid_or_oversized_jsonld']

    indexed = {}
    for node, _ in nodes:
        key = node.get('@id')
        if isinstance(key, str) and set(node) - {'@id', '@context'}:
            # Multiple local definitions are ambiguous; never pick one by input order.
            indexed[key] = {} if key in indexed else node

    result = []
    for node, path in nodes:
        matches = types(node) & KINDS.keys()
        if len(matches) == 1:
            if len(result) == MAX_RESERVATIONS:
                return result, ['too_many_reservations']
            result.append(reservation(node, path, next(iter(matches)), indexed))
    return result, []


class JsonLdHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = []
        self.active = None
        self.truncated = False
        self.template_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'template':
            self.template_depth += 1
        if tag != 'script' or self.template_depth:
            return
        attributes = dict(attrs)
        mime = (attributes.get('type') or '').split(';', 1)[0].strip().lower()
        if mime != 'application/ld+json' or 'src' in attributes:
            return
        if len(self.blocks) >= MAX_BLOCKS:
            self.truncated = True
            return
        self.active = []

    def handle_data(self, data):
        if self.active is not None:
            self.active.append(data)

    def handle_endtag(self, tag):
        if tag == 'template' and self.template_depth:
            self.template_depth -= 1
        if tag == 'script' and self.active is not None:
            self.blocks.append(''.join(self.active))
            self.active = None


def extract_html(text):
    try:
        if len(text.encode('utf-8')) > MAX_INPUT:
            return [], ['html_too_large_for_jsonld']
    except UnicodeError:
        return [], ['invalid_html_encoding_for_jsonld']
    parser = JsonLdHTML()
    parser.feed(text)
    result, warnings = [], []
    if parser.truncated:
        warnings.append('too_many_jsonld_blocks')
    if parser.active is not None:
        warnings.append('unclosed_jsonld_block')
    for index, block in enumerate(parser.blocks):
        reservations, errors = extract_jsonld(block)
        remaining = MAX_RESERVATIONS - len(result)
        if len(reservations) > remaining:
            errors.append('too_many_reservations')
            reservations = reservations[:remaining]
        result.extend({'script_index': index, **item} for item in reservations)
        warnings.extend(errors)
    return result, sorted(set(warnings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='local .jsonld, .json, .html, or .htm file')
    args = parser.parse_args()
    try:
        path = Path(args.input)
        with path.open('rb') as handle:
            data = handle.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise ValueError('input too large')
        suffix = path.suffix.lower()
        if suffix not in {'.jsonld', '.json', '.html', '.htm'}:
            raise ValueError('unsupported input type')
        read = extract_html if suffix in {'.html', '.htm'} else extract_jsonld
        reservations, warnings = read(data.decode('utf-8-sig'))
    except (OSError, ValueError):
        raise SystemExit('INVALID: expected a bounded UTF-8 JSON-LD or HTML file')
    print(json.dumps({'format': 'fotonest.reservation_hints.private', 'version': 1,
                      'reservations': reservations, 'warnings': warnings}, ensure_ascii=False))


if __name__ == '__main__':
    main()
