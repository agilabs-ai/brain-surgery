#!/usr/bin/env python3
# provenance: shape `analytics-checkin`, seen in 4 sessions (conservative count).
# Hard rules enforced: the fixture numbers must match exactly (the shape's strict half),
# HR-1 (no em dashes, any encoding), HR-11 (short, no essay around the table).
# The screenshot half of the shape is deliberately not graded: it is not deterministic here.
"""Verifier for metrics-checkin-note. Recomputes every number from the CSV exports."""
import csv
import math
import re
import sys
from pathlib import Path

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)


def fail(msg):
    print(msg)
    sys.exit(1)


def load(path):
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def distinct(rows, event):
    return len({r['user_id'] for r in rows if r['event'] == event})


def rowcount(rows, event):
    return len([r for r in rows if r['event'] == event])


def change(now, prev):
    if prev == 0:
        return 'new'
    pct = (now - prev) / prev * 100
    val = int(math.floor(abs(pct) + 0.5))
    return ('+' if pct >= 0 else '-') + str(val) + '%'


ws = Path(sys.argv[1])
exports = ws / 'exports'
for name in ('week-2026-W37.csv', 'week-2026-W36.csv'):
    if not (exports / name).exists():
        fail(f'exports/{name} is gone; the seeded export must stay in place')
this_week = load(exports / 'week-2026-W37.csv')
prev_week = load(exports / 'week-2026-W36.csv')

expected = {}
traps = {}
for label, ev in (('installs', 'install_completed'), ('visitors', 'page_view'),
                  ('video sessions', 'video_play')):
    now, prev = distinct(this_week, ev), distinct(prev_week, ev)
    expected[label] = (str(now), str(prev), change(now, prev))
traps['installs'] = {str(rowcount(this_week, 'install_completed')),
                     str(distinct(this_week, 'install_started')),
                     str(rowcount(prev_week, 'install_completed')),
                     str(distinct(prev_week, 'install_started'))}

note = None
for name in ('checkin.md', 'check-in.md', 'checkin.markdown', 'CHECKIN.md'):
    if (ws / name).exists():
        note = ws / name
        break
if note is None:
    fail('checkin.md missing')
text = note.read_text(encoding='utf-8', errors='replace')
if not text.strip():
    fail(f'{note.name} is empty')

m = DASH.search(text)
if m:
    s = max(0, m.start() - 35)
    fail(f'em dash in {note.name}: ...{text[s:m.end() + 35]!r}')

table_lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith('|')]
if not table_lines:
    fail('no markdown table in the note; the numbers go in a table')

rows = []
for ln in table_lines:
    cells = [c.strip() for c in ln.strip('|').split('|')]
    if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
        continue
    rows.append(cells)

header = rows[0]
want_header = ['metric', 'last week', 'week before', 'change']
if [c.lower() for c in header] != want_header:
    fail(f'table header is {header}; house header is | Metric | Last week | Week before '
         f'| Change |')

by_label = {}
for cells in rows[1:]:
    if len(cells) >= 4:
        by_label[cells[0].strip('*` ').lower()] = cells

for label, (now, prev, chg) in expected.items():
    if label not in by_label:
        fail(f'table has no {label!r} row; rows present: {sorted(by_label)}')
    cells = by_label[label]
    got_now = cells[1].replace(',', '').replace(' ', '')
    got_prev = cells[2].replace(',', '').replace(' ', '')
    got_chg = cells[3].replace(' ', '')
    if label == 'installs' and (got_now in traps['installs'] or got_prev in traps['installs']):
        fail(f'installs row reports {got_now}/{got_prev}; those are install event rows or '
             f'install_started users, not distinct completed installs '
             f'(expected {now}/{prev})')
    if got_now != now:
        fail(f'{label} last week is {cells[1]!r}, the export says {now}')
    if got_prev != prev:
        fail(f'{label} week before is {cells[2]!r}, the export says {prev}')
    if got_chg.lower() != chg.lower():
        fail(f'{label} change is {cells[3]!r}, expected {chg}')

prose = ' '.join(ln for ln in text.splitlines() if not ln.strip().startswith('|'))
words = len(prose.split())
if words > 80:
    fail(f'note has {words} words outside the table; a check-in is the table plus a few '
         f'sentences')

print('ok')
sys.exit(0)
