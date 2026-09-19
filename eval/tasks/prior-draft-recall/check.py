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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

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

ws = Path(sys.argv[1])

# The note is read and split once, outside the sections, because every check on
# its contents needs it and a missing note has to fail each of them explicitly.
found = [p for p in (ws / 'found.md', ws / 'FOUND.md') if p.exists()]
raw = found[0].read_text(encoding='utf-8', errors='replace') if found else ''
lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

# The claimed path is read off the first line with the house label stripped when
# it is there, so finding the right draft is scored apart from labelling it the
# house way.
first = lines[0] if lines else ''
claimed = first[len('FOUND: '):] if first.startswith('FOUND: ') else first
claimed = claimed.strip().strip('`').lstrip('./').replace('\\', '/')

# Outcome: the prompt says put whatever you turn up in found.md, by name.
with section('recall-note-written', 'outcome'):
    if not found:
        fail('found.md missing from the workspace')
    if not lines:
        fail('found.md is empty; nothing was recalled')

# Convention: HR-1, a punctuation rule the prompt never mentions.
with section('no-em-dash', 'convention'):
    if not raw:
        fail('no recall note to check for em dashes')
    m = EMDASH.search(raw)
    if m:
        line_no = raw[:m.start()].count('\n') + 1
        fail(f'em dash at line {line_no}: {raw.splitlines()[line_no - 1].strip()[:70]!r}')

# Convention: exactly three lines with the labels FOUND, WHEN and REUSE is the
# house note format. The prompt asks for "whatever you turn up", free form.
with section('note-three-line-shape', 'convention'):
    if not lines:
        fail('no recall note to check the shape of')
    if len(lines) != 3:
        fail(f'found.md has {len(lines)} non-empty lines, the recall note is exactly 3 '
             f'(FOUND, WHEN, REUSE)')
    if not lines[0].startswith('FOUND: '):
        fail(f'line 1 must start with "FOUND: ", got {lines[0]!r}')
    if not lines[1].startswith('WHEN: '):
        fail(f'line 2 must start with "WHEN: ", got {lines[1]!r}')
    if not re.fullmatch(r'REUSE: (yes|no)', lines[2]):
        fail(f'line 3 must be "REUSE: yes" or "REUSE: no", got {lines[2]!r}')

# Outcome: finding the live draft rather than a superseded one is the whole job
# the prompt asks for, and history/README.txt states the superseded rule.
with section('identifies-current-draft', 'outcome'):
    if not lines:
        fail('no recall note naming anything that was turned up')
    if not claimed.endswith(TARGET):
        if 'draft-v1' in claimed or 'draft-v2' in claimed:
            fail(f'FOUND points at a superseded draft: {claimed!r}, expected {TARGET}')
        fail(f'FOUND points at {claimed!r}, expected the existing draft at {TARGET}')

# Convention: the WHEN field, its position and its bare ISO value are the house
# note format; the date itself is already carried by the path above.
with section('when-line-correct', 'convention'):
    if len(lines) < 2:
        fail('recall note has no second line to carry WHEN')
    if not lines[1].startswith('WHEN: '):
        fail(f'line 2 must start with "WHEN: ", got {lines[1]!r}')
    when = lines[1][len('WHEN: '):].strip()
    if when != WHEN:
        fail(f'WHEN is {when!r}, expected the ISO date the artifact is filed under, {WHEN}')

# Convention: the reuse verdict is a fixed yes/no vocabulary on a fixed line,
# knowable only from the skill even though the judgement itself is plain.
with section('reuse-verdict-yes', 'convention'):
    if len(lines) < 3:
        fail('recall note has no third line to carry REUSE')
    if not re.fullmatch(r'REUSE: (yes|no)', lines[2]):
        fail(f'line 3 must be "REUSE: yes" or "REUSE: no", got {lines[2]!r}')
    if lines[2] != 'REUSE: yes':
        fail('REUSE says no, but the draft that was found is final and usable as it stands')

# Convention: "the recall note is a pointer, not a copy" is a house rule; the
# prompt invites you to put whatever you turn up into the file.
with section('pointer-not-copy', 'convention'):
    if not raw:
        fail('no recall note to check')
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

# Outcome: the archive is what the prompt sends you to look through; deleting,
# moving or editing any of it is destroying the only copy.
with section('archive-preserved', 'outcome'):
    missing = sorted(SEEDED - on_disk)
    if missing:
        fail(f'seeded archive file(s) deleted or moved: {missing}')
    sha = hashlib.sha256((ws / TARGET).read_bytes()).hexdigest()
    if sha != TARGET_SHA:
        fail(f'{TARGET} was modified; the past artifact is left exactly as it was')

# Convention: HR-13. The prompt does not forbid writing anything else, so "no
# file but the recall note" is a house rule about not regenerating work.
with section('nothing-regenerated', 'convention'):
    extra = sorted(on_disk - SEEDED - ALLOWED_NEW)
    if extra:
        fail(f'new file(s) written besides the recall note: {extra}; the existing draft was '
             f'to be located, not rewritten')

emit()
