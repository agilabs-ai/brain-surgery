#!/usr/bin/env python3
# provenance: shape `tldr-status-rollup`, seen in 27 sessions (conservative count).
"""Verifier for progress-board-rollup.

Checks the house board: fixed column order, one row per seeded status file,
rows sorted by pct ascending with alphabetical tie-break, the state mapping,
and the trailing OPEN count. Standard library only.
"""
import re
import sys
from pathlib import Path

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)

# Ground truth, derived by hand from tasks/progress-board-rollup/workspace/status/.
EXPECTED_ROWS = [
    ('10', 'cost-report', 'moving'),
    ('10', 'relay-backfill', 'blocked'),
    ('40', 'alert-routing', 'blocked'),
    ('60', 'checkpoint-writer', 'moving'),
    ('100', 'feed-parser', 'done'),
    ('100', 'schema-freeze', 'done'),
]
EXPECTED_OPEN = 4


def fail(msg):
    print(msg)
    sys.exit(1)


def cells(line):
    parts = line.strip().split('|')
    if len(parts) < 2 or parts[0].strip() or parts[-1].strip():
        return None  # a table row starts and ends with a pipe
    return [p.strip() for p in parts[1:-1]]


ws = Path(sys.argv[1])
found = [p for p in (ws / 'board.md', ws / 'BOARD.md') if p.exists()]
if not found:
    fail('board.md missing from the workspace')
raw = found[0].read_text(encoding='utf-8', errors='replace')

m = EMDASH.search(raw)
if m:
    line_no = raw[:m.start()].count('\n') + 1
    fail(f'em dash at line {line_no}: {raw.splitlines()[line_no - 1].strip()[:70]!r}')

lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
if not lines:
    fail('board.md is empty')

if lines[0] != 'BOARD: status':
    fail(f'line 1 must be "BOARD: status", naming the source directory, got {lines[0]!r}')

if len(lines) < 3:
    fail('board.md has no table')

head = cells(lines[1])
if head != ['pct', 'item', 'state']:
    fail(f'header row must be "| pct | item | state |", got {lines[1]!r}')

sep = cells(lines[2])
if sep is None or len(sep) != 3 or not all(re.fullmatch(r':?-{2,}:?', c) for c in sep):
    fail(f'row 3 must be the separator "| --- | --- | --- |", got {lines[2]!r}')

body = lines[3:]
if not body:
    fail('the board has no data rows')

last = body[-1]
mo = re.fullmatch(r'OPEN: (\d+)', last)
if not mo:
    fail(f'last line must be "OPEN: <n>", got {last!r}')
if int(mo.group(1)) != EXPECTED_OPEN:
    fail(f'OPEN count is {mo.group(1)}, expected {EXPECTED_OPEN} (rows with pct under 100)')
rows_raw = body[:-1]

parsed = []
for ln in rows_raw:
    c = cells(ln)
    if c is None:
        fail(f'line between the table and the OPEN line is not a table row: {ln!r}')
    if len(c) != 3:
        fail(f'row has {len(c)} columns, expected 3 (pct, item, state): {ln!r}')
    parsed.append(tuple(c))

if len(parsed) != len(EXPECTED_ROWS):
    fail(f'board has {len(parsed)} rows, expected one per status file ({len(EXPECTED_ROWS)})')

got_items = [r[1] for r in parsed]
want_items = [r[1] for r in EXPECTED_ROWS]
if sorted(got_items) != sorted(want_items):
    missing = sorted(set(want_items) - set(got_items))
    extra = sorted(set(got_items) - set(want_items))
    fail(f'wrong workstreams on the board, missing {missing}, unexpected {extra}')

for i, (got, want) in enumerate(zip(parsed, EXPECTED_ROWS), start=1):
    if got == want:
        continue
    if got[1] != want[1]:
        fail(f'row {i} is {got[1]!r}, expected {want[1]!r}: rows sort by pct ascending, '
             f'ties alphabetical by item')
    if got[0] != want[0]:
        fail(f'row {i} ({want[1]}) has pct {got[0]!r}, expected the bare integer {want[0]!r}')
    fail(f'row {i} ({want[1]}) has state {got[2]!r}, expected {want[2]!r}')

print('ok')
sys.exit(0)
