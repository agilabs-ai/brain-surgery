#!/usr/bin/env python3
# provenance: shape `buffer-cadence-cap-enforcement`, seen in 3 sessions (conservative count).
# Hard rules enforced: HR-2 (max 2 LinkedIn posts per UTC day, and when 2, one morning
# and one afternoon UTC), HR-6 (approved copy is scheduled, never parked as a draft),
# HR-1 (no em dashes, any encoding).
"""Verifier for queue-cadence-cap."""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
ISO = re.compile(r'^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})Z$')
SEED_IDS = {'q-101', 'q-102', 'q-103', 'q-104', 'q-105', 'q-106', 'q-107'}
MARKER = 'nine seconds to recall'


def fail(msg):
    print(msg)
    sys.exit(1)


ws = Path(sys.argv[1])
q = ws / 'queue.json'
if not q.exists():
    fail('queue.json missing')
raw = q.read_text(encoding='utf-8', errors='replace')

m = DASH.search(raw)
if m:
    s = max(0, m.start() - 35)
    fail(f'em dash in queue.json: ...{raw[s:m.end() + 35]!r}')

try:
    posts = json.loads(raw)
except Exception as e:
    fail(f'queue.json is not valid JSON: {e}')
if isinstance(posts, dict) and isinstance(posts.get('posts'), list):
    posts = posts['posts']
if not isinstance(posts, list):
    fail('queue.json must hold a list of post records')
for p in posts:
    if not isinstance(p, dict):
        fail(f'queue entry is not an object: {p!r}')

ids = [str(p.get('id')) for p in posts]
missing = SEED_IDS - set(ids)
if missing:
    fail(f'posts dropped from the queue: {sorted(missing)}; overflow is moved, never deleted')
if len(ids) != len(set(ids)):
    fail(f'duplicate post ids in queue.json: {sorted(i for i in set(ids) if ids.count(i) > 1)}')

new = [p for p in posts if str(p.get('id')) not in SEED_IDS]
if not new:
    fail('the approved post was never added to queue.json')
if len(new) > 1:
    fail(f'{len(new)} new records added, expected one: {[p.get("id") for p in new]}')
np = new[0]
new_body = ' '.join(str(np.get('body', '')).split()).lower()
if MARKER not in new_body:
    fail(f'the new record does not carry the approved copy (looked for {MARKER!r}): '
         f'{str(np.get("body"))[:120]!r}')
if str(np.get('channel', '')).lower() != 'linkedin':
    fail(f'new post channel is {np.get("channel")!r}, expected "linkedin"')
if str(np.get('status', '')).lower() != 'scheduled':
    fail(f'new post status is {np.get("status")!r}; approved copy is scheduled, never a draft')
if not str(np.get('dueAt', '')).startswith('2026-09-22'):
    fail(f'new post dueAt is {np.get("dueAt")!r}; it was asked for on the 22nd')

for p in posts:
    if str(p.get('status', '')).lower() != 'scheduled':
        fail(f'post {p.get("id")!r} has status {p.get("status")!r}; everything on the queue '
             f'is scheduled')
    if not ISO.match(str(p.get('dueAt', ''))):
        fail(f'post {p.get("id")!r} has dueAt {p.get("dueAt")!r}; house form is UTC '
             f'YYYY-MM-DDTHH:MM:SSZ')

li = [p for p in posts if str(p.get('channel', '')).lower() == 'linkedin']
byday = defaultdict(list)
for p in li:
    d, hh, mm, ss = ISO.match(str(p['dueAt'])).groups()
    byday[d].append((int(hh), p['id'], p['dueAt']))

for day in sorted(byday):
    slots = sorted(byday[day])
    if len(slots) > 2:
        fail(f'{day} has {len(slots)} LinkedIn posts ('
             f'{", ".join(i for _, i, _ in slots)}); the cap is 2 per day')
    if len(slots) == 2:
        morning = [s for s in slots if s[0] < 12]
        afternoon = [s for s in slots if s[0] >= 12]
        if len(morning) != 1 or len(afternoon) != 1:
            fail(f'{day} has both posts in the same half of the day ('
                 f'{", ".join(t for _, _, t in slots)}); two posts means one morning UTC '
                 f'and one afternoon UTC')

times = [str(p['dueAt']) for p in li]
dupes = sorted({t for t in times if times.count(t) > 1})
if dupes:
    fail(f'two LinkedIn posts share a dueAt: {dupes}')

print('ok')
sys.exit(0)
