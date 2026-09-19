#!/usr/bin/env python3
# provenance: shape `workplan-write-and-track`, seen in 4 sessions of the mined corpus.
"""Verifier for workplan-authoring.

Offline only. Reads nothing outside the workspace path given as argv[1].
Checks the house workplan format:
  1. the plan is a durable file in the working directory
  2. every step is a checkbox
  3. every step carries an owner and a status from a closed set
  4. the checkbox state agrees with the status token
  5. every owner named in the notes shows up
  6. a Verification section names a command
  plus the house no-em-dash rule, in any encoding
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

ws = Path(sys.argv[1]).resolve()

OWNERS = ('ana', 'kim', 'raul')
STATUSES = ('todo', 'doing', 'blocked', 'done')
MIN_STEPS = 5
DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
STEP = re.compile(r'^\s*[-*]\s*\[( |x|X)\]\s+(.*\S)\s*$')


# The plan and its parsed steps are resolved once, outside the sections, so a
# missing plan fails each section on its own terms instead of stopping the run.
plan = None
named = [p for p in sorted(ws.rglob('*'))
         if p.is_file() and re.search(r'work[ _-]?plan', p.name, re.I) and p.suffix.lower() in ('.md', '.markdown')]
if named:
    plan = named[0]
else:
    for p in sorted(ws.rglob('*.md')):
        if p.name.lower() == 'notes.md':
            continue
        if re.search(r'^#{1,3}\s*steps\b', p.read_text(errors='replace'), re.I | re.M):
            plan = p
            break

body = plan.read_text(errors='replace') if plan is not None else ''

steps = []
for i, line in enumerate(body.splitlines(), 1):
    m = STEP.match(line)
    if m:
        steps.append((i, m.group(1).lower() == 'x', m.group(2)))

# 1. locate the plan.
# Outcome: "can you write a workplan out of ./notes.md ... keep everything in
# this directory" is the request, in the prompt, in those words, and the
# locator accepts any markdown plan, however it is named or laid out.
with section('workplan-written', 'outcome'):
    if plan is None:
        fail('no workplan markdown file in the working directory')

# Convention: the no-em-dash house rule is nowhere in the prompt.
with section('no-em-dash', 'convention'):
    if plan is None:
        fail('no workplan to check for em dashes')
    m = DASH.search(body)
    if m:
        n = body[:m.start()].count('\n') + 1
        fail('em dash at line %d: %r' % (n, body.splitlines()[n - 1].strip()[:80]))

# 2. every step is a checkbox.
# Convention: the notes carry six work items so the count itself is
# discoverable, but this check only counts "- [ ]" lines, and "every step is a
# checkbox" is a house rule the prompt never states. Plain bullets fail.
with section('steps-are-checkboxes', 'convention'):
    if plan is None:
        fail('no workplan to count steps in')
    bullets = [ln for ln in body.splitlines() if re.match(r'^\s*[-*]\s+(?!\[)', ln)]
    if len(steps) < MIN_STEPS:
        extra = ' (%d plain bullets found; every step is a checkbox)' % len(bullets) if bullets else ''
        fail('workplan has %d checkbox steps, expected at least %d%s' % (len(steps), MIN_STEPS, extra))

# 3. owner and status tokens.
# Convention: the "@owner" token, the "[status: ...]" token and the closed
# vocabulary todo/doing/blocked/done are house format end to end.
with section('step-owner-and-status', 'convention'):
    if plan is None:
        fail('no workplan to read steps from')
    if not steps:
        fail('workplan has no checkbox steps to carry an owner and a status')
    for lineno, checked, text in steps:
        owners = re.findall(r'@([A-Za-z][A-Za-z0-9_-]*)', text)
        if len(owners) != 1:
            fail('step on line %d needs exactly one @owner token, found %d: %r'
                 % (lineno, len(owners), text[:80]))
        st = re.findall(r'\[status:\s*([A-Za-z]+)\s*\]', text)
        if len(st) != 1:
            fail('step on line %d needs exactly one [status:...] token, found %d: %r'
                 % (lineno, len(st), text[:80]))
        status = st[0].lower()
        if status not in STATUSES:
            fail('step on line %d has status %r, which is not one of %s'
                 % (lineno, st[0], ', '.join(STATUSES)))

# 4. the tick agrees with the status token.
# Convention: internal consistency is a correctness property, but it can only
# be reached through the house checkbox and [status:...] tokens, so an agent
# without the skill cannot pass it however careful it is.
with section('checkbox-matches-status', 'convention'):
    if plan is None:
        fail('no workplan to check checkbox state in')
    if not steps:
        fail('workplan has no checkbox steps to agree with a status')
    for lineno, checked, text in steps:
        st = re.findall(r'\[status:\s*([A-Za-z]+)\s*\]', text)
        if len(st) != 1:
            continue  # already reported by step-owner-and-status
        status = st[0].lower()
        if checked and status != 'done':
            fail('step on line %d is ticked [x] but its status is %r' % (lineno, status))
        if not checked and status == 'done':
            fail('step on line %d has status done but its checkbox is not ticked' % lineno)

# 5. every owner from the notes appears.
# Convention: covering everyone named in notes.md is discoverable from the
# seeded notes, but ownership is only counted through the "@name" token, so a
# plan that writes "Ana: split the upload" fails. The house syntax is the gate.
with section('every-owner-assigned', 'convention'):
    if plan is None:
        fail('no workplan to read owners from')
    assigned = {o.lower() for _, _, t in steps for o in re.findall(r'@([A-Za-z][A-Za-z0-9_-]*)', t)}
    missing = [o for o in OWNERS if o not in assigned]
    if missing:
        fail('no step assigned to %s; everyone named in the notes owns something'
             % ', '.join('@' + o for o in missing))

# 6. the verification section.
# Convention: the prompt asks for a workplan out of the notes and never for a
# verification step, and the "$ " command-line marker is a house format string.
with section('verification-command', 'convention'):
    if plan is None:
        fail('no workplan to look for a Verification section in')
    m = re.search(r'^#{1,6}\s*verification\b(.*?)(?=^#{1,6}\s|\Z)', body, re.I | re.M | re.S)
    if not m:
        fail('workplan has no ## Verification section')
    if not re.search(r'^\s*\$ \S', m.group(1), re.M):
        fail('the Verification section names no command; it needs at least one "$ " command line')

emit()
