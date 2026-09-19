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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
THREAD_ID = '4f21c8'
RESUME_CMD = 'bsr-resume 4f21c8 --from step-7'
WANT_SECTIONS = ['## STATE', '## DONE', '## OPEN', '## RESUME']


ws = Path(sys.argv[1])

# The note, and everything derived from it, is resolved once outside the
# sections so a missing or malformed file fails each section on its own terms.
found = [p for p in (ws / 'handoff.md', ws / 'HANDOFF.md') if p.exists()]
raw = found[0].read_text(encoding='utf-8', errors='replace') if found else ''
lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
heads = [(i, ln) for i, ln in enumerate(lines) if ln.startswith('#')]
blocks = {}
for n, (i, name) in enumerate(heads):
    end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
    blocks[name] = lines[i + 1:end]

# Outcome: the prompt names the file, "Write handoff.md here", in those words.
with section('handoff-written', 'outcome'):
    if not found:
        fail('handoff.md missing from the workspace')
    if not lines:
        fail('handoff.md is empty')

# Convention: the no-em-dash house rule is nowhere in the prompt and nothing in
# prior/ hints at it.
with section('no-em-dash', 'convention'):
    if not raw:
        fail('no handoff.md to check for em dashes')
    m = EMDASH.search(raw)
    if m:
        line_no = raw[:m.start()].count('\n') + 1
        fail(f'em dash at line {line_no}: {raw.splitlines()[line_no - 1].strip()[:70]!r}')

# Outcome: prior/thread-4f21c8.md says in words that /tmp/importer-cache is a
# throwaway, is stale and is not to be trusted, and names work/rows.json as the
# copy that matters. Handing the next person a dead scratch path is a real
# correctness failure and the workspace states it plainly.
with section('no-scratch-paths', 'outcome'):
    if not raw:
        fail('no handoff.md to check for scratch paths')
    if '/tmp' in raw:
        line_no = raw[:raw.index('/tmp')].count('\n') + 1
        fail(f'handoff names a scratch path under /tmp at line {line_no}: '
             f'{raw.splitlines()[line_no - 1].strip()[:70]!r}')

# Convention: the exact "HANDOFF <id>" first line is a house format string; the
# prompt gives the thread id but never this shape.
with section('first-line-thread-id', 'convention'):
    if not lines:
        fail('no handoff.md content to read a first line from')
    if lines[0] != f'HANDOFF {THREAD_ID}':
        fail(f'line 1 must be "HANDOFF {THREAD_ID}", got {lines[0]!r}')

# Convention: four named sections in a mandated order is exactly the kind of
# rule that lives only in the skill.
with section('sections-exact-and-ordered', 'convention'):
    if not lines:
        fail('no handoff.md content to read sections from')
    got_sections = [ln for _, ln in heads]
    if got_sections != WANT_SECTIONS:
        fail(f'sections must be exactly {WANT_SECTIONS} in that order, got {got_sections}')

# Convention: the one-line, 25-word STATE budget is a house format rule.
with section('state-one-line', 'convention'):
    if '## STATE' not in blocks:
        fail('no ## STATE section in the handoff')
    state = blocks['## STATE']
    if len(state) != 1:
        fail(f'## STATE must be exactly one line, got {len(state)}')
    if len(state[0].split()) > 25:
        fail(f'## STATE is {len(state[0].split())} words, the handoff format allows at most 25')

# Convention: one-line "- " bullets in named DONE and OPEN blocks is house
# layout; the prompt asks only that the next person not start cold.
with section('done-and-open-bulleted', 'convention'):
    for name in ('## DONE', '## OPEN'):
        if name not in blocks:
            fail(f'no {name} section in the handoff')
        items = blocks[name]
        if not items:
            fail(f'{name} block is empty')
        for it in items:
            if not it.startswith('- '):
                fail(f'{name} block line is not a "- " bullet on one line: {it!r}')
            if len(it) < 12:
                fail(f'{name} bullet is empty or near empty: {it!r}')

# Convention: the resume command itself is in prior/thread-4f21c8.md, so
# carrying it is discoverable, but this check only passes when it sits alone in
# a "## RESUME" section wrapped in backticks, which is house format.
with section('resume-command', 'convention'):
    if '## RESUME' not in blocks:
        fail('no ## RESUME section in the handoff')
    resume = blocks['## RESUME']
    if len(resume) != 1:
        fail(f'## RESUME must be exactly one line holding the resume command, got {len(resume)}')
    if RESUME_CMD not in resume[0]:
        fail(f'## RESUME does not carry the resume command {RESUME_CMD!r}, got {resume[0]!r}')
    if not (resume[0].startswith('`') and resume[0].endswith('`')):
        fail(f'## RESUME line must be wrapped in backticks, got {resume[0]!r}')

emit()
