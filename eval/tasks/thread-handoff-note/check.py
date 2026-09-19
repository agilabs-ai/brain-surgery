#!/usr/bin/env python3
# provenance: shape `session-continuation-handoff`, seen in 10 sessions (conservative count).
"""Verifier for thread-handoff-note.

Checks the house handoff note: the `HANDOFF <id>` first line, exactly four
sections in a fixed order, a one line STATE, bulleted DONE and OPEN, the resume
command in RESUME, and no scratch paths handed on. Standard library only.
"""
import re
import sys
from pathlib import Path

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
THREAD_ID = '4f21c8'
RESUME_CMD = 'bsr-resume 4f21c8 --from step-7'
WANT_SECTIONS = ['## STATE', '## DONE', '## OPEN', '## RESUME']


def fail(msg):
    print(msg)
    sys.exit(1)


ws = Path(sys.argv[1])
found = [p for p in (ws / 'handoff.md', ws / 'HANDOFF.md') if p.exists()]
if not found:
    fail('handoff.md missing from the workspace')
raw = found[0].read_text(encoding='utf-8', errors='replace')

m = EMDASH.search(raw)
if m:
    line_no = raw[:m.start()].count('\n') + 1
    fail(f'em dash at line {line_no}: {raw.splitlines()[line_no - 1].strip()[:70]!r}')

if '/tmp' in raw:
    line_no = raw[:raw.index('/tmp')].count('\n') + 1
    fail(f'handoff names a scratch path under /tmp at line {line_no}: '
         f'{raw.splitlines()[line_no - 1].strip()[:70]!r}')

lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
if not lines:
    fail('handoff.md is empty')

if lines[0] != f'HANDOFF {THREAD_ID}':
    fail(f'line 1 must be "HANDOFF {THREAD_ID}", got {lines[0]!r}')

heads = [(i, ln) for i, ln in enumerate(lines) if ln.startswith('#')]
got_sections = [ln for _, ln in heads]
if got_sections != WANT_SECTIONS:
    fail(f'sections must be exactly {WANT_SECTIONS} in that order, got {got_sections}')

blocks = {}
for n, (i, name) in enumerate(heads):
    end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
    blocks[name] = lines[i + 1:end]

state = blocks['## STATE']
if len(state) != 1:
    fail(f'## STATE must be exactly one line, got {len(state)}')
if len(state[0].split()) > 25:
    fail(f'## STATE is {len(state[0].split())} words, the handoff format allows at most 25')

for name in ('## DONE', '## OPEN'):
    items = blocks[name]
    if not items:
        fail(f'{name} block is empty')
    for it in items:
        if not it.startswith('- '):
            fail(f'{name} block line is not a "- " bullet on one line: {it!r}')
        if len(it) < 12:
            fail(f'{name} bullet is empty or near empty: {it!r}')

resume = blocks['## RESUME']
if len(resume) != 1:
    fail(f'## RESUME must be exactly one line holding the resume command, got {len(resume)}')
if RESUME_CMD not in resume[0]:
    fail(f'## RESUME does not carry the resume command {RESUME_CMD!r}, got {resume[0]!r}')
if not (resume[0].startswith('`') and resume[0].endswith('`')):
    fail(f'## RESUME line must be wrapped in backticks, got {resume[0]!r}')

print('ok')
sys.exit(0)
