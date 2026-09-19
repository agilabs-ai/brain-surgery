#!/usr/bin/env python3
# provenance: shape `workplan-write-and-track`, seen in 4 sessions of the mined corpus.
"""Verifier for workplan-authoring.

Offline only. Reads nothing outside the workspace path given as argv[1].
Checks the house workplan format:
  1. the plan is a durable file in the working directory
  2. every step is a checkbox carrying an owner and a status from a closed set
  3. the checkbox state agrees with the status token
  4. every owner named in the notes shows up
  5. a Verification section names a command
  6. no em dashes (house rule, any encoding)
"""
import re
import sys
from pathlib import Path

ws = Path(sys.argv[1]).resolve()

OWNERS = ('ana', 'kim', 'raul')
STATUSES = ('todo', 'doing', 'blocked', 'done')
MIN_STEPS = 5
DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
STEP = re.compile(r'^\s*[-*]\s*\[( |x|X)\]\s+(.*\S)\s*$')


def fail(msg):
    print(msg)
    sys.exit(1)


# 1. locate the plan
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
if plan is None:
    fail('no workplan markdown file in the working directory')

body = plan.read_text(errors='replace')

m = DASH.search(body)
if m:
    n = body[:m.start()].count('\n') + 1
    fail('em dash at line %d: %r' % (n, body.splitlines()[n - 1].strip()[:80]))

# 2 and 3. the steps
steps = []
for i, line in enumerate(body.splitlines(), 1):
    m = STEP.match(line)
    if m:
        steps.append((i, m.group(1).lower() == 'x', m.group(2)))

bullets = [ln for ln in body.splitlines() if re.match(r'^\s*[-*]\s+(?!\[)', ln)]
if len(steps) < MIN_STEPS:
    extra = ' (%d plain bullets found; every step is a checkbox)' % len(bullets) if bullets else ''
    fail('workplan has %d checkbox steps, expected at least %d%s' % (len(steps), MIN_STEPS, extra))

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
    if checked and status != 'done':
        fail('step on line %d is ticked [x] but its status is %r' % (lineno, status))
    if not checked and status == 'done':
        fail('step on line %d has status done but its checkbox is not ticked' % lineno)

# 4. every owner from the notes appears
assigned = {o.lower() for _, _, t in steps for o in re.findall(r'@([A-Za-z][A-Za-z0-9_-]*)', t)}
missing = [o for o in OWNERS if o not in assigned]
if missing:
    fail('no step assigned to %s; everyone named in the notes owns something'
         % ', '.join('@' + o for o in missing))

# 5. the verification section
m = re.search(r'^#{1,6}\s*verification\b(.*?)(?=^#{1,6}\s|\Z)', body, re.I | re.M | re.S)
if not m:
    fail('workplan has no ## Verification section')
if not re.search(r'^\s*\$ \S', m.group(1), re.M):
    fail('the Verification section names no command; it needs at least one "$ " command line')

print('ok')
sys.exit(0)
