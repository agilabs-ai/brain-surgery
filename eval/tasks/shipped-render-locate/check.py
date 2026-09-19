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


def fail(msg):
    print(msg)
    sys.exit(1)


ws = Path(sys.argv[1])
found = [p for p in (ws / 'pointer.txt', ws / 'POINTER.txt') if p.exists()]
if not found:
    fail('pointer.txt missing from the workspace')
raw = found[0].read_text(encoding='utf-8', errors='replace')

m = EMDASH.search(raw)
if m:
    fail(f'em dash in pointer.txt: {raw.strip()[:70]!r}')
if '/tmp' in raw:
    fail('pointer.txt names a scratch render path under /tmp; the answer is the archive path')

lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
if len(lines) != 1:
    fail(f'pointer.txt has {len(lines)} non-empty lines, the pointer is exactly one line')

parts = lines[0].split(' :: ')
if len(parts) != 3:
    fail(f'pointer must be three fields separated by " :: ", got {lines[0]!r}')
got_id, got_date, got_path = (p.strip().strip('`') for p in parts)

if got_id != WANT_ID:
    if got_id in ('mf-0422', 'mf-0409'):
        fail(f'pointer names {got_id}, which was never published; the build that went out is {WANT_ID}')
    fail(f'pointer names build {got_id!r}, expected {WANT_ID!r}')
if got_date != WANT_DATE:
    fail(f'pointer carries date {got_date!r}, expected the build date {WANT_DATE!r}')
got_path = got_path.replace('\\', '/').lstrip('./')
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

missing = sorted(SEEDED - on_disk)
if missing:
    fail(f'seeded archive file(s) deleted or moved: {missing}')
extra = sorted(on_disk - SEEDED - ALLOWED_NEW)
if extra:
    fail(f'new file(s) written besides the pointer: {extra}; the existing build was to be '
         f'located, not rebuilt or copied')
if hashlib.sha256((ws / 'archive' / 'mf-0417.json').read_bytes()).hexdigest() != MANIFEST_SHA:
    fail('archive/mf-0417.json was modified; the archive is left exactly as it was')

print('ok')
sys.exit(0)
