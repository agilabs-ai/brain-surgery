#!/usr/bin/env python3
# provenance: shape `find-past-artifact-in-history`, seen in 8 sessions (conservative count).
"""Verifier for shipped-render-locate.

Checks the one line house pointer, that it names the published build rather
than the newer unpublished one, that it cites the archive path rather than the
scratch render path, and that nothing was rebuilt. Standard library only.
"""
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)

WANT_ID = 'mf-0417'
WANT_DATE = '2026-03-04'
WANT_PATH = 'media/2026-03/quarter-recap-v2.mp4'
MANIFEST_SHA = 'de4ff36a0c91b96a6a7ff41d526c7f43bfedc261e1e8c12113710a24965e0ff9'
SEEDED = {
    'archive/README.txt',
    'archive/mf-0401.json',
    'archive/mf-0409.json',
    'archive/mf-0417.json',
    'archive/mf-0422.json',
    'archive/mf-0430.json',
    'media/2026-02/quarter-recap-v1.mp4',
    'media/2026-02/team-intro-v1.mp4',
    'media/2026-03/quarter-recap-v2.mp4',
    'media/2026-03/quarter-recap-v3.mp4',
    'media/2026-04/hiring-clip-v1.mp4',
}
ALLOWED_NEW = {'pointer.txt', 'POINTER.txt'}

ws = Path(sys.argv[1])
found = [p for p in (ws / 'pointer.txt', ws / 'POINTER.txt') if p.exists()]
raw = found[0].read_text(encoding='utf-8', errors='replace') if found else ''

# The three pointer fields are parsed once, outside the sections; each section
# that reads them says so itself when the pointer is missing or malformed.
lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
parts = lines[0].split(' :: ') if lines else []
fields = [p.strip().strip('`') for p in parts] if len(parts) == 3 else None

# 1. the pointer file itself.
# Outcome: "Put the answer in pointer.txt" is the request, in the prompt, in
# those words.
with section('pointer-written', 'outcome'):
    if not found:
        fail('pointer.txt missing from the workspace')
    if not lines:
        fail('pointer.txt is empty')

# Convention: HR-1. The prompt asks where a file lives, never for a punctuation rule.
with section('no-em-dash', 'convention'):
    if not found:
        fail('no pointer.txt to check for em dashes')
    m = EMDASH.search(raw)
    if m:
        fail(f'em dash in pointer.txt: {raw.strip()[:70]!r}')

# 2. the one line, three field house shape.
# Convention: one line of "id :: date :: path" separated by " :: " is a house
# format string; the prompt asks a question and never describes an answer shape.
with section('pointer-shape', 'convention'):
    if not lines:
        fail('no pointer.txt to read')
    if len(lines) != 1:
        fail(f'pointer.txt has {len(lines)} non-empty lines, the pointer is exactly one line')
    if fields is None:
        fail(f'pointer must be three fields separated by " :: ", got {lines[0]!r}')

# 3. the build that actually shipped.
# Outcome: the prompt asks for "the one that actually went out in March", so
# naming an unpublished build is a wrong answer to the question that was asked.
with section('names-published-build', 'outcome'):
    if fields is None:
        fail('no parsable pointer line to read a build id from')
    got_id = fields[0]
    if got_id != WANT_ID:
        if got_id in ('mf-0422', 'mf-0409'):
            fail(f'pointer names {got_id}, which was never published; the build that went '
                 f'out is {WANT_ID}')
        fail(f'pointer names build {got_id!r}, expected {WANT_ID!r}')

# 4. the build date.
# Outcome: "in March" is the discriminator the prompt gives, and the date is
# recorded in the archive manifests the agent has to read to answer at all.
with section('build-date-correct', 'outcome'):
    if fields is None:
        fail('no parsable pointer line to read a date from')
    got_date = fields[1]
    if got_date != WANT_DATE:
        fail(f'pointer carries date {got_date!r}, expected the build date {WANT_DATE!r}')

# 5. where it lives.
# Outcome: "Where does it live?" is the question; a scratch path under /tmp is
# not where it lives, and any careful agent checks the path it hands over.
with section('cites-archive-path', 'outcome'):
    if '/tmp' in raw:
        fail('pointer.txt names a scratch render path under /tmp; the answer is the archive path')
    if fields is None:
        fail('no parsable pointer line to read a path from')
    got_path = fields[2].replace('\\', '/').lstrip('./')
    if not got_path.endswith(WANT_PATH):
        fail(f'pointer cites {got_path!r}, expected the archive path {WANT_PATH!r}')

on_disk = set()
for p in ws.rglob('*'):
    if p.is_dir():
        continue
    rel = p.relative_to(ws).as_posix()
    if any(part.startswith('.') for part in rel.split('/')):
        continue
    on_disk.add(rel)

# 6. the archive survived the lookup.
# Outcome: a lookup that deletes or edits the thing it was sent to find is the
# real failure mode, whatever the house procedure says.
with section('archive-intact', 'outcome'):
    missing = sorted(SEEDED - on_disk)
    if missing:
        fail(f'seeded archive file(s) deleted or moved: {missing}')
    if hashlib.sha256((ws / 'archive' / 'mf-0417.json').read_bytes()).hexdigest() != MANIFEST_SHA:
        fail('archive/mf-0417.json was modified; the archive is left exactly as it was')

# 7. nothing else was written.
# Convention: the prompt asks where the clip lives and never forbids working
# files, so "the pointer is the only new file" is a local rule, not a stated one.
with section('nothing-rebuilt', 'convention'):
    extra = sorted(on_disk - SEEDED - ALLOWED_NEW)
    if extra:
        fail(f'new file(s) written besides the pointer: {extra}; the existing build was to be '
             f'located, not rebuilt or copied')

emit()
