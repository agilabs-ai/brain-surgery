#!/usr/bin/env python3
# provenance: shape `first-comment-link`, seen in 5 sessions (conservative count).
# Hard rules enforced: HR-3 (product site link only, never a code host or an install
# command), HR-1 (no em dashes, any encoding), HR-6 (the record stays scheduled).
"""Verifier for first-comment-link."""
import json
import re
import sys
from pathlib import Path

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
URL = re.compile(r'https?://[^\s<>()\[\]"\',]+')
SITE = 'https://toolshelf.example/'
ENTITY_ID = 'urn:org:5512347'


def fail(msg):
    print(msg)
    sys.exit(1)


ws = Path(sys.argv[1])
p = ws / 'queue' / 'scheduled-post.json'
if not p.exists():
    fail('queue/scheduled-post.json missing')
raw = p.read_text(encoding='utf-8', errors='replace')
try:
    rec = json.loads(raw)
except Exception as e:
    fail(f'queue/scheduled-post.json is not valid JSON: {e}')
if not isinstance(rec, dict):
    fail('queue/scheduled-post.json must stay a single JSON object')

for key in ('id', 'channel', 'dueAt', 'status', 'body', 'firstComment', 'mentions'):
    if key not in rec:
        fail(f'record lost key {key!r}; keys present: {sorted(rec)}')
if rec['id'] != 'p-8812' or rec['dueAt'] != '2026-09-19T08:30:00Z':
    fail(f'id/dueAt were changed: id={rec["id"]!r} dueAt={rec["dueAt"]!r}')
if str(rec['status']).lower() != 'scheduled':
    fail(f'status is {rec["status"]!r}; the post was already scheduled and stays scheduled')

body = str(rec['body'])
fc = str(rec['firstComment'] or '')

if not fc.strip():
    fail('firstComment is empty; the download link belongs there')

for label, text in (('body', body), ('firstComment', fc)):
    m = DASH.search(text)
    if m:
        s = max(0, m.start() - 35)
        fail(f'em dash in {label}: ...{text[s:m.end() + 35]!r}')

fc_urls = URL.findall(fc)
if not fc_urls:
    fail(f'firstComment carries no link: {fc[:120]!r}')
for u in fc_urls:
    if not u.startswith(SITE):
        fail(f'firstComment links {u!r}; it must be the product page on {SITE}')
if not any(u.rstrip('/').endswith('/tools/quickstash') for u in fc_urls):
    fail(f'firstComment does not link the Quickstash product page: {fc_urls}')

low_fc = fc.lower()
for bad in ('npx ', 'repo.example', 'github.com'):
    if bad in low_fc:
        fail(f'firstComment contains {bad!r}; no code host links, no install commands')

body_urls = URL.findall(body)
if body_urls:
    fail(f'post body still carries a link ({body_urls[0]!r}); the link lives in the first comment')
low_body = body.lower()
for bad in ('npx ', 'repo.example', 'github.com'):
    if bad in low_body:
        fail(f'post body contains {bad!r}; no code host links, no install commands')

if 'northpin' not in low_body:
    fail('post body never mentions Northpin; the readable @Northpin belongs in the body')

mentions = rec['mentions']
if not isinstance(mentions, list) or not mentions:
    fail('mentions is empty; a tag needs the partner entityId to notify anyone')
blob = json.dumps(mentions)
if ENTITY_ID not in blob:
    fail(f'mentions does not carry Northpin entityId {ENTITY_ID!r}: {blob[:160]}')

print('ok')
sys.exit(0)
