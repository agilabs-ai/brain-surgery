#!/usr/bin/env python3
# provenance: integration fixture, authored 2026-09-19. Not derived from session logs
# and not evidence about any setup. Exists to prove the adapters, configuration
# control, scoring contract and report work end to end.
"""Verifier for csv-rollup.

Every check here is `outcome`: each one tests something the prompt states in words.
The prompt names the status filter, the deduplication, the month, the per-region
counts and totals, the rounding and the output shape. Nothing is withheld, which is
the rule for a generated performance case and the opposite of the legacy corpus in
`eval/tasks/`.

The one `indicator` check asks whether the candidate procedure was followed, by
looking for the row-count reasoning it prescribes. It is evidence that the mechanism
activated, never part of the score, because a procedure firing is not a task
succeeding.

Ground truth is recomputed from the fixture rather than hard-coded, so the checker
and the CSV cannot drift apart.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eval'))
from checklib import fail, report as emit, section  # noqa: E402

ws = Path(sys.argv[1]).resolve()
SRC = ws / 'orders.csv'
OUT = ws / 'rollup.json'


def truth():
    rows = list(csv.DictReader(SRC.open()))
    seen, keep = set(), []
    for r in rows:
        if r['status'] != 'shipped':
            continue
        if not r['placed_on'].startswith('2026-08'):
            continue
        if r['order_id'] in seen:
            continue
        seen.add(r['order_id'])
        keep.append(r)
    agg = {}
    for r in keep:
        a = agg.setdefault(r['region'], {'orders': 0, 'total_eur': 0.0})
        a['orders'] += 1
        a['total_eur'] = round(a['total_eur'] + float(r['amount_eur']), 2)
    return agg, len(rows)


# Read the artifact once, outside the sections, so a missing or malformed file makes
# each dependent section fail for its own reason rather than crashing the verifier.
EXPECTED, RAW_ROWS = (truth() if SRC.exists() else ({}, 0))
doc = None
parse_error = None
if OUT.exists():
    try:
        doc = json.loads(OUT.read_text(errors='replace'))
    except ValueError as e:
        parse_error = str(e)

with section('rollup-written', 'outcome'):
    if not OUT.exists():
        fail('rollup.json was not written; the prompt names it as the output file')
    if parse_error:
        fail('rollup.json is not valid JSON: %s' % parse_error)
    if not isinstance(doc, dict) or not isinstance(doc.get('regions'), dict):
        fail('rollup.json has no top-level "regions" object; the prompt gives the shape')

regions = (doc or {}).get('regions') if isinstance(doc, dict) else None
regions = regions if isinstance(regions, dict) else {}

with section('regions-present', 'outcome'):
    missing = sorted(set(EXPECTED) - set(regions))
    extra = sorted(set(regions) - set(EXPECTED))
    if missing:
        fail('rollup.json is missing region(s) %s' % ', '.join(missing))
    if extra:
        fail('rollup.json has region(s) %s that no qualifying order belongs to' % ', '.join(extra))

with section('order-counts-correct', 'outcome'):
    for name, want in sorted(EXPECTED.items()):
        got = regions.get(name)
        if not isinstance(got, dict):
            fail('region %s is not an object' % name)
        if got.get('orders') != want['orders']:
            fail('region %s has orders %r, expected %d (shipped only, each order_id once, '
                 'August 2026 only)' % (name, got.get('orders'), want['orders']))

with section('totals-correct', 'outcome'):
    for name, want in sorted(EXPECTED.items()):
        got = regions.get(name) or {}
        value = got.get('total_eur')
        if not isinstance(value, (int, float)):
            fail('region %s total_eur is %r, which is not a number' % (name, value))
        if round(float(value), 2) != want['total_eur']:
            fail('region %s total_eur is %s, expected %s'
                 % (name, value, want['total_eur']))

with section('source-unmodified', 'outcome'):
    if not SRC.exists():
        fail('orders.csv was deleted; the prompt asks for a rollup, not an edit')
    if len(list(csv.DictReader(SRC.open()))) != RAW_ROWS:
        fail('orders.csv row count changed; the source export is not to be edited')

# Not part of the score. The procedure asks for raw, filtered and deduplicated counts
# to be kept; if the agent recorded them, the procedure demonstrably reached it.
with section('procedure-followed', 'indicator'):
    trace = ' '.join(p.read_text(errors='replace')
                     for p in sorted(ws.rglob('*'))
                     if p.is_file() and p.suffix in ('.md', '.txt', '.json')
                     and p.name != 'orders.csv')
    if str(RAW_ROWS) not in trace:
        fail('no record of the raw row count; the candidate procedure asks for counts '
             'before and after each filter')

emit()
