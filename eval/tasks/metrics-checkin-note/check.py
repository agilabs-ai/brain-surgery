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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)


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

# The exports, the note and the parsed table are all read once, outside the sections,
# because every section below needs them and each has to report their absence itself.
missing_exports = [n for n in ('week-2026-W37.csv', 'week-2026-W36.csv')
                   if not (exports / n).exists()]
expected = {}
traps = {}
if not missing_exports:
    try:
        this_week = load(exports / 'week-2026-W37.csv')
        prev_week = load(exports / 'week-2026-W36.csv')
        for label, ev in (('installs', 'install_completed'), ('visitors', 'page_view'),
                          ('video sessions', 'video_play')):
            now, prev = distinct(this_week, ev), distinct(prev_week, ev)
            expected[label] = (str(now), str(prev), change(now, prev))
        traps['installs'] = {str(rowcount(this_week, 'install_completed')),
                             str(distinct(this_week, 'install_started')),
                             str(rowcount(prev_week, 'install_completed')),
                             str(distinct(prev_week, 'install_started'))}
    except (OSError, UnicodeError, KeyError, csv.Error):
        expected = {}
        traps = {}

note = None
for name in ('checkin.md', 'check-in.md', 'checkin.markdown', 'CHECKIN.md'):
    if (ws / name).exists():
        note = ws / name
        break
text = note.read_text(encoding='utf-8', errors='replace') if note else ''

table_lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith('|')]
rows = []
for ln in table_lines:
    cells = [c.strip() for c in ln.strip('|').split('|')]
    if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
        continue
    rows.append(cells)
header = rows[0] if rows else None
by_label = {}
for cells in rows[1:]:
    if len(cells) >= 4:
        by_label[cells[0].strip('*` ').lower()] = cells


def cells_for(label):
    """Return the table row for a label, failing the enclosing section if it cannot."""
    if not expected:
        fail('the seeded exports under exports/ could not be read, so no number can be verified')
    if note is None:
        fail('checkin.md missing')
    if label not in by_label:
        fail(f'table has no {label!r} row; rows present: {sorted(by_label)}')
    return by_label[label]


def counts(label, cells):
    return (cells[1].replace(',', '').replace(' ', ''),
            cells[2].replace(',', '').replace(' ', ''))


# Outcome: the exports are the user's data and the prompt only asks to read them; a
# careful agent does not delete its inputs.
with section('exports-preserved', 'outcome'):
    for name in missing_exports:
        fail(f'exports/{name} is gone; the seeded export must stay in place')

# Outcome: "put it in checkin.md" is the prompt, filename included, and an empty note
# answers nothing.
with section('checkin-written', 'outcome'):
    if note is None:
        fail('checkin.md missing')
    if not text.strip():
        fail(f'{note.name} is empty')

# Convention: HR-1. The prompt says nothing about punctuation.
with section('no-em-dash', 'convention'):
    if note is None:
        fail('checkin.md missing')
    m = DASH.search(text)
    if m:
        s = max(0, m.start() - 35)
        fail(f'em dash in {note.name}: ...{text[s:m.end() + 35]!r}')

# Convention: the prompt asks for numbers, not for a table; "the numbers go in a table"
# is the house shape.
with section('table-present', 'convention'):
    if note is None:
        fail('checkin.md missing')
    if not table_lines:
        fail('no markdown table in the note; the numbers go in a table')

# Convention: the exact four column names, in that order, are a house header string.
with section('table-header', 'convention'):
    if note is None:
        fail('checkin.md missing')
    if header is None:
        fail('no markdown table in the note; the numbers go in a table')
    want_header = ['metric', 'last week', 'week before', 'change']
    if [c.lower() for c in header] != want_header:
        fail(f'table header is {header}; house header is | Metric | Last week | Week before '
             f'| Change |')

# Outcome: "where did installs land last week vs the week before" is the prompt, and the
# trap is the difference between started and completed installs, which is simply correct
# or incorrect arithmetic over the export.
with section('installs-exact', 'outcome'):
    cells = cells_for('installs')
    now, prev, _chg = expected['installs']
    got_now, got_prev = counts('installs', cells)
    if got_now in traps['installs'] or got_prev in traps['installs']:
        fail(f'installs row reports {got_now}/{got_prev}; those are install event rows or '
             f'install_started users, not distinct completed installs '
             f'(expected {now}/{prev})')
    if got_now != now:
        fail(f'installs last week is {cells[1]!r}, the export says {now}')
    if got_prev != prev:
        fail(f'installs week before is {cells[2]!r}, the export says {prev}')

# Outcome: "is the video stuff even being tracked, i'd like to see that" is the prompt.
with section('video-sessions-exact', 'outcome'):
    cells = cells_for('video sessions')
    now, prev, _chg = expected['video sessions']
    got_now, got_prev = counts('video sessions', cells)
    if got_now != now:
        fail(f'video sessions last week is {cells[1]!r}, the export says {now}')
    if got_prev != prev:
        fail(f'video sessions week before is {cells[2]!r}, the export says {prev}')

# Convention: the prompt asks about installs and video only; the visitors row is a
# required part of the house check-in that nobody asked for.
with section('visitors-row', 'convention'):
    cells = cells_for('visitors')
    now, prev, _chg = expected['visitors']
    got_now, got_prev = counts('visitors', cells)
    if got_now != now:
        fail(f'visitors last week is {cells[1]!r}, the export says {now}')
    if got_prev != prev:
        fail(f'visitors week before is {cells[2]!r}, the export says {prev}')

# Convention: a percent change column, its rounding and the +/- and "new" spellings are
# the house format; the prompt asks for the two numbers, not for a computed delta string.
with section('change-column', 'convention'):
    if not expected:
        fail('the seeded exports under exports/ could not be read, so no number can be verified')
    for label in sorted(expected):
        cells = cells_for(label)
        chg = expected[label][2]
        got_chg = cells[3].replace(' ', '')
        if got_chg.lower() != chg.lower():
            fail(f'{label} change is {cells[3]!r}, expected {chg}')

# Convention: HR-11. The prompt never asks for brevity; the 80 word ceiling is a house rule.
with section('prose-budget', 'convention'):
    if note is None:
        fail('checkin.md missing')
    prose = ' '.join(ln for ln in text.splitlines() if not ln.strip().startswith('|'))
    words = len(prose.split())
    if words > 80:
        fail(f'note has {words} words outside the table; a check-in is the table plus a few '
             f'sentences')

emit()
