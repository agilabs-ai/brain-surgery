#!/usr/bin/env python3
# provenance: shape `tldr-status-rollup`, seen in 27 sessions (conservative count).
"""Verifier for history-rollup-brief.

Checks the house rollup skeleton: a `# ROLLUP <slug>` title line, a bare
`SCORE: <int>` line, bare `DONE` and `OPEN` blocks of one-line bullets in that
order, and a single trailing `NEXT:` line. Standard library only.
"""
import re
import sys
from pathlib import Path

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)


def fail(msg):
    print(msg)
    sys.exit(1)


ws = Path(sys.argv[1])
cands = [ws / 'rollup.md', ws / 'ROLLUP.md', ws / 'rollup.MD']
found = [c for c in cands if c.exists()]
if not found:
    fail('rollup.md missing from the workspace')
raw = found[0].read_text(encoding='utf-8', errors='replace')

if '```' in raw:
    fail('rollup.md contains a code fence; the rollup is plain lines only')
m = EMDASH.search(raw)
if m:
    line_no = raw[:m.start()].count('\n') + 1
    ctx = raw.splitlines()[line_no - 1].strip()[:70]
    fail(f'em dash at line {line_no}: {ctx!r}')

lines = [ln.rstrip() for ln in raw.splitlines()]
lines = [ln for ln in lines if ln.strip()]
if not lines:
    fail('rollup.md is empty')
if len(lines) > 20:
    fail(f'rollup.md has {len(lines)} non-empty lines, the rollup format allows at most 20')

if not re.fullmatch(r'# ROLLUP [a-z0-9]+(-[a-z0-9]+)*', lines[0]):
    fail(f'line 1 must be "# ROLLUP <slug>" with a lowercase hyphenated slug, got {lines[0]!r}')

if len(lines) < 2:
    fail('rollup.md has no SCORE line')
if not re.fullmatch(r'SCORE: (100|[0-9]{1,2})', lines[1]):
    fail(f'line 2 must be "SCORE: <integer 0-100>", got {lines[1]!r}')

if len(lines) < 3 or lines[2] != 'DONE':
    got = lines[2] if len(lines) > 2 else '<end of file>'
    fail(f'line 3 must be the bare word "DONE", got {got!r}')

try:
    open_at = lines.index('OPEN', 3)
except ValueError:
    fail('no bare "OPEN" line after the DONE block')

done_items = lines[3:open_at]
open_items = lines[open_at + 1:]
if not open_items or not open_items[-1].startswith('NEXT: '):
    last = open_items[-1] if open_items else '<end of file>'
    fail(f'last line must be "NEXT: <action>", got {last!r}')
next_lines = [ln for ln in lines if ln.startswith('NEXT:')]
if len(next_lines) != 1:
    fail(f'expected exactly one NEXT line, found {len(next_lines)}')
if len(open_items[-1].split()) < 3:
    fail(f'NEXT line names no real action: {open_items[-1]!r}')
open_items = open_items[:-1]

for label, items in (('DONE', done_items), ('OPEN', open_items)):
    if not items:
        fail(f'the {label} block has no items')
    if len(items) > 6:
        fail(f'the {label} block has {len(items)} items, the rollup format allows at most 6')
    for it in items:
        if not it.startswith('- '):
            fail(f'{label} block line is not a "- " bullet on one line: {it!r}')
        if len(it) < 12:
            fail(f'{label} bullet is empty or near empty: {it!r}')

print('ok')
sys.exit(0)
