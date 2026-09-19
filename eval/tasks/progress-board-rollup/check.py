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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

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


def cells(line):
    parts = line.strip().split('|')
    if len(parts) < 2 or parts[0].strip() or parts[-1].strip():
        return None  # a table row starts and ends with a pipe
    return [p.strip() for p in parts[1:-1]]


ws = Path(sys.argv[1])
found = [p for p in (ws / 'board.md', ws / 'BOARD.md') if p.exists()]
raw = found[0].read_text(encoding='utf-8', errors='replace') if found else ''
lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]

# The table body and its rows are parsed once, outside the sections, because
# every later section needs them and each one guards on its own.
body = lines[3:]
open_match = re.fullmatch(r'OPEN: (\d+)', body[-1]) if body else None
rows_raw = body[:-1] if open_match else body
parsed = []
bad_rows = []
for ln in rows_raw:
    c = cells(ln)
    if c is None or len(c) != 3:
        bad_rows.append((ln, c))
    else:
        parsed.append(tuple(c))
by_item = {}
for c in parsed:
    by_item.setdefault(c[1], c)

# 1. the board file exists and has something in it.
# Outcome: "written to board.md" is the request, in the prompt, in those words.
with section('board-written', 'outcome'):
    if not found:
        fail('board.md missing from the workspace')
    if not lines:
        fail('board.md is empty')

# Convention: HR-1. The prompt asks for a board, never for a punctuation rule.
with section('no-em-dash', 'convention'):
    if not found:
        fail('no board.md to check for em dashes')
    m = EMDASH.search(raw)
    if m:
        line_no = raw[:m.start()].count('\n') + 1
        fail(f'em dash at line {line_no}: {raw.splitlines()[line_no - 1].strip()[:70]!r}')

# 2. the house title line.
# Convention: "BOARD: status" is a fixed format string; the prompt names no header at all.
with section('board-title-line', 'convention'):
    if not lines:
        fail('no board.md to read a title line from')
    if lines[0] != 'BOARD: status':
        fail(f'line 1 must be "BOARD: status", naming the source directory, got {lines[0]!r}')

# 3. the fixed column set and order.
# Convention: the column names pct/item/state and their order exist only in the skill.
with section('board-table-header', 'convention'):
    if not lines:
        fail('no board.md to read a header from')
    if len(lines) < 3:
        fail('board.md has no table')
    head = cells(lines[1])
    if head != ['pct', 'item', 'state']:
        fail(f'header row must be "| pct | item | state |", got {lines[1]!r}')
    sep = cells(lines[2])
    if sep is None or len(sep) != 3 or not all(re.fullmatch(r':?-{2,}:?', c) for c in sep):
        fail(f'row 3 must be the separator "| --- | --- | --- |", got {lines[2]!r}')

# 4. every data line is a three column table row.
# Convention: the pipe-table row shape is part of the same house format as the header.
with section('board-rows-are-table-rows', 'convention'):
    if not lines:
        fail('no board.md to read rows from')
    if not rows_raw:
        fail('the board has no data rows')
    for ln, c in bad_rows:
        if c is None:
            fail(f'line between the table and the OPEN line is not a table row: {ln!r}')
        fail(f'row has {len(c)} columns, expected 3 (pct, item, state): {ln!r}')

# 5. one row per workstream, none missing and none invented.
# Outcome: the prompt says status/ has one file per workstream and asks for "the
# board, all of it", so covering every workstream is the stated job.
with section('board-covers-every-workstream', 'outcome'):
    if not lines:
        fail('no board.md to read rows from')
    got_items = [r[1] for r in parsed]
    want_items = [r[1] for r in EXPECTED_ROWS]
    if sorted(got_items) != sorted(want_items):
        missing = sorted(set(want_items) - set(got_items))
        extra = sorted(set(got_items) - set(want_items))
        fail(f'wrong workstreams on the board, missing {missing}, unexpected {extra}')
    if len(parsed) != len(EXPECTED_ROWS):
        fail(f'board has {len(parsed)} rows, expected one per status file ({len(EXPECTED_ROWS)})')

# 6. the pct carried across from the status file.
# Outcome: each status file states "pct: N" in those words; reporting where
# everything stands is the request, and a wrong number is a wrong answer.
with section('row-pct-values', 'outcome'):
    if not parsed:
        fail('no board rows to read a pct from')
    for i, want in enumerate(EXPECTED_ROWS, start=1):
        got = by_item.get(want[1])
        if got is None:
            fail(f'no row for {want[1]!r}, so its pct {want[0]!r} is not on the board')
        if got[0] != want[0]:
            fail(f'row {i} ({want[1]}) has pct {got[0]!r}, expected the bare integer {want[0]!r}')

# 7. the state word.
# Convention: moving/blocked/done is a fixed vocabulary, and the rule that maps a
# blocker line and a pct onto one of those three words is only in the skill.
with section('row-state-values', 'convention'):
    if not parsed:
        fail('no board rows to read a state from')
    for i, want in enumerate(EXPECTED_ROWS, start=1):
        got = by_item.get(want[1])
        if got is None:
            fail(f'no row for {want[1]!r}, so its state {want[2]!r} is not on the board')
        if got[2] != want[2]:
            fail(f'row {i} ({want[1]}) has state {got[2]!r}, expected {want[2]!r}')

# 8. the row order.
# Convention: a mandated sort key, pct ascending with an alphabetical tie-break,
# which the prompt never states.
with section('rows-sorted', 'convention'):
    if not parsed:
        fail('no board rows to check the order of')
    for i, (got, want) in enumerate(zip(parsed, EXPECTED_ROWS), start=1):
        if got[1] != want[1]:
            fail(f'row {i} is {got[1]!r}, expected {want[1]!r}: rows sort by pct ascending, '
                 f'ties alphabetical by item')

# 9. the trailing OPEN count.
# Convention: a required footer line, with its own format, that the prompt never
# asks for; the prompt in fact asks for "no commentary".
with section('open-count', 'convention'):
    if not body:
        fail('no board.md to read an OPEN line from')
    last = body[-1]
    if not open_match:
        fail(f'last line must be "OPEN: <n>", got {last!r}')
    if int(open_match.group(1)) != EXPECTED_OPEN:
        fail(f'OPEN count is {open_match.group(1)}, expected {EXPECTED_OPEN} '
             f'(rows with pct under 100)')

emit()
