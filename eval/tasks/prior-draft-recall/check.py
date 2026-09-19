#!/usr/bin/env python3
# provenance: shape `find-past-artifact-in-history`, seen in 8 sessions (conservative count).
"""Verifier for prior-draft-recall.

Checks the house recall note (FOUND / WHEN / REUSE, three lines, nothing else),
that it points at the one non superseded draft, and the negative half: the
archive is untouched and nothing was regenerated. Standard library only.
"""
import hashlib
import re
import sys
from pathlib import Path

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)

TARGET = 'history/2026-04-12-launch-copy/draft-v3.md'
WHEN = '2026-04-12'
SENTINEL = 'queue that empties itself'
TARGET_SHA = '2cef7acb095c8ba60e45b103d2db3421a3d569251588b83506e55871540132b3'
SEEDED = {
    'history/2026-01-18-pricing-page/notes.md',
    'history/2026-02-20-launch-timeline/plan.md',
    'history/2026-03-03-support-macros/macros.md',
    'history/2026-04-12-launch-copy/draft-v1.md',
    'history/2026-04-12-launch-copy/draft-v2.md',
    'history/2026-04-12-launch-copy/draft-v3.md',
    'history/2026-05-02-onboarding-emails/sequence.md',
    'history/2026-06-09-pricing-experiment/readme.md',
    'history/2026-07-21-launch-retro/retro.md',
    'history/README.txt',
}
ALLOWED_NEW = {'found.md', 'FOUND.md'}


def fail(msg):
    print(msg)
    sys.exit(1)


ws = Path(sys.argv[1])

found = [p for p in (ws / 'found.md', ws / 'FOUND.md') if p.exists()]
if not found:
    fail('found.md missing from the workspace')
raw = found[0].read_text(encoding='utf-8', errors='replace')

m = EMDASH.search(raw)
if m:
    line_no = raw[:m.start()].count('\n') + 1
    fail(f'em dash at line {line_no}: {raw.splitlines()[line_no - 1].strip()[:70]!r}')

lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
if len(lines) != 3:
    fail(f'found.md has {len(lines)} non-empty lines, the recall note is exactly 3 '
         f'(FOUND, WHEN, REUSE)')

if not lines[0].startswith('FOUND: '):
    fail(f'line 1 must start with "FOUND: ", got {lines[0]!r}')
path = lines[0][len('FOUND: '):].strip().strip('`').lstrip('./')
path = path.replace('\\', '/')
if not path.endswith(TARGET):
    if 'draft-v1' in path or 'draft-v2' in path:
        fail(f'FOUND points at a superseded draft: {path!r}, expected {TARGET}')
    fail(f'FOUND points at {path!r}, expected the existing draft at {TARGET}')

if not lines[1].startswith('WHEN: '):
    fail(f'line 2 must start with "WHEN: ", got {lines[1]!r}')
when = lines[1][len('WHEN: '):].strip()
if when != WHEN:
    fail(f'WHEN is {when!r}, expected the ISO date the artifact is filed under, {WHEN}')

if not re.fullmatch(r'REUSE: (yes|no)', lines[2]):
    fail(f'line 3 must be "REUSE: yes" or "REUSE: no", got {lines[2]!r}')
if lines[2] != 'REUSE: yes':
    fail('REUSE says no, but the draft that was found is final and usable as it stands')

if SENTINEL in raw:
    fail('found.md reproduces the draft text; the recall note is a pointer, not a copy')

# Negative half: nothing regenerated, nothing edited.
on_disk = set()
for p in ws.rglob('*'):
    if p.is_dir():
        continue
    rel = p.relative_to(ws).as_posix()
    if any(part.startswith('.') for part in rel.split('/')):
        continue  # tool droppings, not the agent's answer
    on_disk.add(rel)

missing = sorted(SEEDED - on_disk)
if missing:
    fail(f'seeded archive file(s) deleted or moved: {missing}')

extra = sorted(on_disk - SEEDED - ALLOWED_NEW)
if extra:
    fail(f'new file(s) written besides the recall note: {extra}; the existing draft was '
         f'to be located, not rewritten')

sha = hashlib.sha256((ws / TARGET).read_bytes()).hexdigest()
if sha != TARGET_SHA:
    fail(f'{TARGET} was modified; the past artifact is left exactly as it was')

print('ok')
sys.exit(0)
