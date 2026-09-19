#!/usr/bin/env python3
# provenance: shape `real-chrome-readonly-inspect`, seen in 5 sessions of the mined corpus.
"""Verifier for session-readonly-inspect.

Offline only. Reads nothing outside the workspace path given as argv[1] and never
opens a browser or a socket. Checks the house read-only inspection report:
  1. the snapshot is unchanged (read only really means read only)
  2. the answer file opens with the count, no preamble
  3. one numbered line per tab, titles verbatim and in order
  4. the conclusion is backed by an evidence line quoted from the page
  5. the report closes by declaring that nothing was mutated
"""
import json
import re
import sys
from pathlib import Path

ws = Path(sys.argv[1]).resolve()

TABS = [
    'Team Inbox',
    'Partner Portal (signed out)',
    'Partner Portal',
    'Release notes 4.2',
]
EVIDENCE = 'Signed in as Northwind Freight (workspace: nf-prod)'
ACCOUNT = 'Northwind Freight'
SNAPSHOT_FILES = {
    'tabs.json',
    'pages/t-1.html',
    'pages/t-2.html',
    'pages/t-3.html',
    'pages/t-4.html',
}


def fail(msg):
    print(msg)
    sys.exit(1)


# 1. the snapshot is untouched
sess = ws / 'session'
if not sess.is_dir():
    fail('session/ is gone; the snapshot is read only')
found = {str(p.relative_to(sess)) for p in sess.rglob('*') if p.is_file()}
if found != SNAPSHOT_FILES:
    added = sorted(found - SNAPSHOT_FILES)
    removed = sorted(SNAPSHOT_FILES - found)
    fail('the snapshot was mutated (added: %s, removed: %s); a read only inspection leaves it alone'
         % (added or 'none', removed or 'none'))
try:
    doc = json.loads((sess / 'tabs.json').read_text())
except json.JSONDecodeError as e:
    fail('session/tabs.json no longer parses: %s' % e)
if [t.get('title') for t in doc.get('tabs', [])] != TABS:
    fail('session/tabs.json was edited; a read only inspection leaves it alone')
if EVIDENCE not in (sess / 'pages' / 't-3.html').read_text():
    fail('session/pages/t-3.html was edited; a read only inspection leaves it alone')

# 2. the answer file
ans = ws / 'answer.txt'
if not ans.exists():
    for cand in sorted(ws.glob('*')):
        if cand.is_file() and re.fullmatch(r'answer\.(md|text)', cand.name, re.I):
            ans = cand
            break
if not ans.exists():
    fail('answer.txt was not written')
raw = ans.read_text(errors='replace')
lines = [ln.rstrip() for ln in raw.splitlines()]
body = [ln for ln in lines if ln.strip()]
if not body:
    fail('answer.txt is empty')

m = re.fullmatch(r'tabs:\s*(\d+)', body[0].strip())
if not m:
    fail('answer.txt must open with the tab count line "tabs: N", found %r' % body[0].strip()[:80])
if int(m.group(1)) != len(TABS):
    fail('tab count is %s, the snapshot has %d tabs' % (m.group(1), len(TABS)))

# 3. the numbered tab list, verbatim and in order
if len(body) < 1 + len(TABS):
    fail('answer.txt does not list all %d tabs' % len(TABS))
for i, title in enumerate(TABS):
    line = body[1 + i].strip()
    m = re.fullmatch(r'(\d+)[.)]\s+(.*)', line)
    if not m:
        fail('line %d of answer.txt should be "%d. %s", found %r' % (2 + i, i + 1, title, line[:80]))
    if int(m.group(1)) != i + 1:
        fail('tab list is out of order at line %d: expected item %d, found %s' % (2 + i, i + 1, m.group(1)))
    if m.group(2).strip() != title:
        fail('tab %d title is %r, the snapshot says %r' % (i + 1, m.group(2).strip()[:80], title))

rest = body[1 + len(TABS):]

# 4. conclusion plus quoted evidence
answer_lines = [ln for ln in rest if ln.strip().lower().startswith('answer:')]
if not answer_lines:
    fail('answer.txt has no "answer:" line')
if ACCOUNT not in ' '.join(answer_lines):
    fail('the answer line does not name the signed in account %r' % ACCOUNT)

ev_lines = [ln for ln in rest if ln.strip().lower().startswith('evidence:')]
if not ev_lines:
    fail('answer.txt has no "evidence:" line; a read only finding records what was on the page')
if not any(EVIDENCE in ln for ln in ev_lines):
    fail('the evidence line does not quote the page verbatim; it has to carry %r' % EVIDENCE)

# 5. the mutations footer
if not re.fullmatch(r'mutations:\s*none', body[-1].strip(), re.I):
    fail('answer.txt must close with the line "mutations: none", found %r' % body[-1].strip()[:80])

print('ok')
sys.exit(0)
