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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

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

# 1. the snapshot is untouched.
# Outcome: "read only please, do not change anything in the snapshot" is the
# request, in the prompt, in those words.
with section('snapshot-untouched', 'outcome'):
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

# The answer file and its lines are resolved once, outside the sections, because
# every section below reads them and each one guards on its own.
ans = ws / 'answer.txt'
if not ans.exists():
    for cand in sorted(ws.glob('*')):
        if cand.is_file() and re.fullmatch(r'answer\.(md|text)', cand.name, re.I):
            ans = cand
            break
raw = ans.read_text(errors='replace') if ans.exists() else ''
lines = [ln.rstrip() for ln in raw.splitlines()]
body = [ln for ln in lines if ln.strip()]
count_match = re.fullmatch(r'tabs:\s*(\d+)', body[0].strip()) if body else None
rest = body[1 + len(TABS):]

# 2. the answer file exists and has content.
# Outcome: "put it in answer.txt here" is the request, in the prompt, in those words.
with section('answer-written', 'outcome'):
    if not ans.exists():
        fail('answer.txt was not written')
    if not body:
        fail('answer.txt is empty')

# 3a. the opening line shape.
# Convention: the prompt asks how many tabs are open, but "tabs: N" as the first
# line with no preamble is a house format only the skill states.
with section('answer-opens-with-count', 'convention'):
    if not body:
        fail('no answer.txt to read an opening line from')
    if not count_match:
        fail('answer.txt must open with the tab count line "tabs: N", found %r'
             % body[0].strip()[:80])

# 3b. the count itself.
# Outcome: "how many tabs are open" is the first thing the prompt asks; a wrong
# count is a wrong answer.
with section('tab-count-correct', 'outcome'):
    if not count_match:
        fail('no "tabs: N" count line to read the tab count from')
    if int(count_match.group(1)) != len(TABS):
        fail('tab count is %s, the snapshot has %d tabs' % (count_match.group(1), len(TABS)))

# The tab list lines, parsed once for the two sections that read them.
listed = []
for i in range(len(TABS)):
    line = body[1 + i].strip() if len(body) > 1 + i else None
    listed.append((line, re.fullmatch(r'(\d+)[.)]\s+(.*)', line) if line else None))

# 4a. the numbered list shape.
# Convention: one numbered line per tab, in order, directly under the count line
# is a house layout; the prompt asks what the tabs are and says nothing of form.
with section('tab-list-numbered', 'convention'):
    if not body:
        fail('no answer.txt to read a tab list from')
    if len(body) < 1 + len(TABS):
        fail('answer.txt does not list all %d tabs' % len(TABS))
    for i, (line, m) in enumerate(listed):
        if not m:
            fail('line %d of answer.txt should be "%d. %s", found %r'
                 % (2 + i, i + 1, TABS[i], (line or '')[:80]))
        if int(m.group(1)) != i + 1:
            fail('tab list is out of order at line %d: expected item %d, found %s'
                 % (2 + i, i + 1, m.group(1)))

# 4b. the titles themselves.
# Outcome: "what are they" is the request; the titles are in the snapshot and
# transcribing them wrong is a wrong answer.
with section('tab-titles-verbatim', 'outcome'):
    if not body:
        fail('no answer.txt to read tab titles from')
    for i, (line, m) in enumerate(listed):
        if not m:
            fail('answer.txt does not list tab %d, %r' % (i + 1, TABS[i]))
        if m.group(2).strip() != TABS[i]:
            fail('tab %d title is %r, the snapshot says %r'
                 % (i + 1, m.group(2).strip()[:80], TABS[i]))

answer_lines = [ln for ln in rest if ln.strip().lower().startswith('answer:')]
ev_lines = [ln for ln in rest if ln.strip().lower().startswith('evidence:')]

# 5a. the conclusion line shape.
# Convention: an "answer:" prefixed line after the tab list is a house layout the
# prompt never describes.
with section('answer-line-present', 'convention'):
    if not body:
        fail('no answer.txt to read a conclusion from')
    if not answer_lines:
        fail('answer.txt has no "answer:" line')

# 5b. the account name.
# Outcome: "am i signed in on the partner portal, under which account name" is
# the second question the prompt asks, in those words.
with section('signed-in-account-named', 'outcome'):
    if not answer_lines:
        fail('no "answer:" line to read the signed in account from')
    if ACCOUNT not in ' '.join(answer_lines):
        fail('the answer line does not name the signed in account %r' % ACCOUNT)

# 6. the quoted evidence.
# Convention: the prompt asks a question and never asks the answer to be sourced;
# an "evidence:" line quoting the page verbatim is the skill's own rule.
with section('evidence-quoted', 'convention'):
    if not body:
        fail('no answer.txt to read evidence from')
    if not ev_lines:
        fail('answer.txt has no "evidence:" line; a read only finding records what was on the page')
    if not any(EVIDENCE in ln for ln in ev_lines):
        fail('the evidence line does not quote the page verbatim; it has to carry %r' % EVIDENCE)

# 7. the mutations footer.
# Convention: a required closing line the prompt never mentions; the prompt asks
# for read only behaviour, not for a declaration about it.
with section('mutations-footer', 'convention'):
    if not body:
        fail('no answer.txt to read a footer from')
    if not re.fullmatch(r'mutations:\s*none', body[-1].strip(), re.I):
        fail('answer.txt must close with the line "mutations: none", found %r' % body[-1].strip()[:80])

emit()
