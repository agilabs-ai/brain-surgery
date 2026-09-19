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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)

ws = Path(sys.argv[1])
cands = [ws / 'rollup.md', ws / 'ROLLUP.md', ws / 'rollup.MD']
found = [c for c in cands if c.exists()]

# The file and its line structure are computed once, outside the sections, because every
# section below depends on them and each one has to report a missing file for itself.
raw = found[0].read_text(encoding='utf-8', errors='replace') if found else ''
lines = [ln.rstrip() for ln in raw.splitlines()]
lines = [ln for ln in lines if ln.strip()]

try:
    open_at = lines.index('OPEN', 3)
except ValueError:
    open_at = None
done_items = lines[3:open_at] if open_at is not None else []
tail = lines[open_at + 1:] if open_at is not None else []
open_items = tail[:-1] if tail and tail[-1].startswith('NEXT:') else tail

# Outcome: "Put it in rollup.md in this directory" is the prompt, filename included, and
# an empty file answers nothing.
with section('rollup-written', 'outcome'):
    if not found:
        fail('rollup.md missing from the workspace')
    if not lines:
        fail('rollup.md is empty')

# Convention: "plain lines only" is a house format rule; nothing in the prompt rules out
# a fenced block.
with section('no-code-fence', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    if '```' in raw:
        fail('rollup.md contains a code fence; the rollup is plain lines only')

# Convention: the prompt says nothing about punctuation; the dash ban is a house rule.
with section('no-em-dash', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    m = EMDASH.search(raw)
    if m:
        line_no = raw[:m.start()].count('\n') + 1
        ctx = raw.splitlines()[line_no - 1].strip()[:70]
        fail(f'em dash at line {line_no}: {ctx!r}')

# Convention: "read it on my phone" argues for brevity, but the exact ceiling of 20
# non-empty lines is a number only the skill carries.
with section('line-budget', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    if len(lines) > 20:
        fail(f'rollup.md has {len(lines)} non-empty lines, the rollup format allows at most 20')

# Convention: the "# ROLLUP <slug>" title line, and the lowercase hyphenated slug in it,
# are a house format string the prompt never describes.
with section('title-line', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    if not lines:
        fail('rollup.md is empty')
    if not re.fullmatch(r'# ROLLUP [a-z0-9]+(-[a-z0-9]+)*', lines[0]):
        fail(f'line 1 must be "# ROLLUP <slug>" with a lowercase hyphenated slug, got {lines[0]!r}')

# Convention: the prompt does ask "Where do we stand, 0-100?", but this check tests the
# bare "SCORE: <int>" string at line 2, which is the house format, not the answer.
with section('score-line', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    if len(lines) < 2:
        fail('rollup.md has no SCORE line')
    if not re.fullmatch(r'SCORE: (100|[0-9]{1,2})', lines[1]):
        fail(f'line 2 must be "SCORE: <integer 0-100>", got {lines[1]!r}')

# Convention: bare DONE then bare OPEN, in that order, is a mandated section skeleton
# that exists only in the skill.
with section('done-open-skeleton', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    if len(lines) < 3 or lines[2] != 'DONE':
        got = lines[2] if len(lines) > 2 else '<end of file>'
        fail(f'line 3 must be the bare word "DONE", got {got!r}')
    if open_at is None:
        fail('no bare "OPEN" line after the DONE block')

# Convention: a single trailing "NEXT: <action>" line is a house format string; the
# prompt asks where things stand, not for a next action in a fixed slot.
with section('next-line', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    if open_at is None:
        fail('no bare "OPEN" line after the DONE block')
    if not tail or not tail[-1].startswith('NEXT: '):
        last = tail[-1] if tail else '<end of file>'
        fail(f'last line must be "NEXT: <action>", got {last!r}')
    next_lines = [ln for ln in lines if ln.startswith('NEXT:')]
    if len(next_lines) != 1:
        fail(f'expected exactly one NEXT line, found {len(next_lines)}')
    if len(tail[-1].split()) < 3:
        fail(f'NEXT line names no real action: {tail[-1]!r}')

# Convention: one-line "- " bullets, at most six per block, is the house item format.
with section('bullet-blocks', 'convention'):
    if not found:
        fail('rollup.md missing from the workspace')
    if open_at is None:
        fail('no bare "OPEN" line after the DONE block')
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

emit()
