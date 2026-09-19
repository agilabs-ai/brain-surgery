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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
ISO = re.compile(r'^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})Z$')
SEED_IDS = {'q-101', 'q-102', 'q-103', 'q-104', 'q-105', 'q-106', 'q-107'}
MARKER = 'nine seconds to recall'

ws = Path(sys.argv[1])
q = ws / 'queue.json'
raw = q.read_text(encoding='utf-8', errors='replace') if q.exists() else ''

# The queue is parsed once, outside the sections, because every section below
# reads it and each one guards on its own when it did not parse.
posts = None
parse_error = None
if not q.exists():
    parse_error = 'queue.json missing'
else:
    try:
        loaded = json.loads(raw)
    except Exception as e:  # noqa: BLE001 - reported as a failed check below
        loaded = None
        parse_error = f'queue.json is not valid JSON: {e}'
    if parse_error is None:
        if isinstance(loaded, dict) and isinstance(loaded.get('posts'), list):
            loaded = loaded['posts']
        if not isinstance(loaded, list):
            parse_error = 'queue.json must hold a list of post records'
        elif any(not isinstance(p, dict) for p in loaded):
            bad = next(p for p in loaded if not isinstance(p, dict))
            parse_error = f'queue entry is not an object: {bad!r}'
        else:
            posts = loaded

# 1. the queue still exists and still parses.
# Outcome: the prompt names queue.json as the thing to edit, and leaving it
# unparsable is the plainest way to break the job that was asked for.
with section('queue-parses', 'outcome'):
    if parse_error:
        fail(parse_error)

# Convention: HR-1. The prompt asks for a scheduling change, never a punctuation rule.
with section('no-em-dash', 'convention'):
    if not q.exists():
        fail('no queue.json to check for em dashes')
    m = DASH.search(raw)
    if m:
        s = max(0, m.start() - 35)
        fail(f'em dash in queue.json: ...{raw[s:m.end() + 35]!r}')

ids = [str(p.get('id')) for p in posts] if posts is not None else []
new = [p for p in posts if str(p.get('id')) not in SEED_IDS] if posts is not None else []
np = new[0] if len(new) == 1 else None

# 2. nothing already on the queue was lost.
# Outcome: destroying queued posts while de-crowding the week is the real failure
# mode, and no prompt has to say "do not delete my data".
with section('seed-preserved', 'outcome'):
    if posts is None:
        fail('queue.json did not parse, so the seeded posts cannot be accounted for')
    missing = SEED_IDS - set(ids)
    if missing:
        fail(f'posts dropped from the queue: {sorted(missing)}; overflow is moved, never deleted')
    if len(ids) != len(set(ids)):
        fail(f'duplicate post ids in queue.json: {sorted(i for i in set(ids) if ids.count(i) > 1)}')

# 3. the approved copy landed on the queue, once.
# Outcome: "The approved copy is in approved/metrics-post.md. Put it on the
# LinkedIn queue in queue.json" is the request, in the prompt, in those words.
with section('approved-post-added', 'outcome'):
    if posts is None:
        fail('queue.json did not parse, so the approved post cannot be found')
    if not new:
        fail('the approved post was never added to queue.json')
    if len(new) > 1:
        fail(f'{len(new)} new records added, expected one: {[p.get("id") for p in new]}')
    new_body = ' '.join(str(new[0].get('body', '')).split()).lower()
    if MARKER not in new_body:
        fail(f'the new record does not carry the approved copy (looked for {MARKER!r}): '
             f'{str(new[0].get("body"))[:120]!r}')

# 4. on the right channel, on the right day.
# Outcome: "the LinkedIn queue ... for the 22nd" is the request, in those words.
with section('approved-post-channel-and-date', 'outcome'):
    if np is None:
        fail('no single new queue record to check the channel and date of')
    if str(np.get('channel', '')).lower() != 'linkedin':
        fail(f'new post channel is {np.get("channel")!r}, expected "linkedin"')
    if not str(np.get('dueAt', '')).startswith('2026-09-22'):
        fail(f'new post dueAt is {np.get("dueAt")!r}; it was asked for on the 22nd')

# 5. scheduled, not parked as a draft.
# Outcome: "put it on the queue" is what the prompt asks, and every seeded record
# already carries status "scheduled", so the value is readable off the workspace.
with section('approved-post-scheduled', 'outcome'):
    if np is None:
        fail('no single new queue record to check the status of')
    if str(np.get('status', '')).lower() != 'scheduled':
        fail(f'new post status is {np.get("status")!r}; approved copy is scheduled, '
             f'never a draft')

# 6. nothing else was demoted while the week was de-crowded.
# Outcome: moving an overflowing post is the job; quietly turning someone else's
# scheduled post into a draft loses it from the queue in all but name.
with section('all-posts-scheduled', 'outcome'):
    if posts is None:
        fail('queue.json did not parse, so post statuses cannot be read')
    for p in posts:
        if str(p.get('status', '')).lower() != 'scheduled':
            fail(f'post {p.get("id")!r} has status {p.get("status")!r}; everything on the queue '
                 f'is scheduled')

# 7. the timestamp form.
# Convention: the prompt says nothing about timestamps; "UTC YYYY-MM-DDTHH:MM:SSZ"
# is the house form (it is visible in the seeded records, but stated only in the skill).
with section('dueAt-iso-utc', 'convention'):
    if posts is None:
        fail('queue.json did not parse, so dueAt values cannot be read')
    for p in posts:
        if not ISO.match(str(p.get('dueAt', ''))):
            fail(f'post {p.get("id")!r} has dueAt {p.get("dueAt")!r}; house form is UTC '
                 f'YYYY-MM-DDTHH:MM:SSZ')

li = [p for p in (posts or []) if str(p.get('channel', '')).lower() == 'linkedin']
byday = defaultdict(list)
for p in li:
    m = ISO.match(str(p.get('dueAt', '')))
    if m:
        d, hh, mm, ss = m.groups()
        byday[d].append((int(hh), str(p.get('id')), str(p.get('dueAt'))))

# 8. the daily cap.
# Convention: the prompt says the week "looks crowded ... sort it out" and never
# names a number; the cap of 2 LinkedIn posts per UTC day is HR-2, from the skill.
with section('linkedin-daily-cap', 'convention'):
    if posts is None:
        fail('queue.json did not parse, so the daily cadence cannot be counted')
    for day in sorted(byday):
        slots = sorted(byday[day])
        if len(slots) > 2:
            fail(f'{day} has {len(slots)} LinkedIn posts ('
                 f'{", ".join(i for _, i, _ in slots)}); the cap is 2 per day')

# 9. the shape of a two post day.
# Convention: "when there are two, one morning UTC and one afternoon UTC" is HR-2
# again, a rule the prompt never hints at.
with section('linkedin-day-split', 'convention'):
    if posts is None:
        fail('queue.json did not parse, so the daily cadence cannot be counted')
    for day in sorted(byday):
        slots = sorted(byday[day])
        if len(slots) == 2:
            morning = [s for s in slots if s[0] < 12]
            afternoon = [s for s in slots if s[0] >= 12]
            if len(morning) != 1 or len(afternoon) != 1:
                fail(f'{day} has both posts in the same half of the day ('
                     f'{", ".join(t for _, _, t in slots)}); two posts means one morning UTC '
                     f'and one afternoon UTC')

# 10. no two posts in the same slot.
# Outcome: two LinkedIn posts at the identical timestamp is a collision any
# careful agent avoids, and de-crowding the week is what the prompt asked for.
with section('no-duplicate-slots', 'outcome'):
    if posts is None:
        fail('queue.json did not parse, so slot collisions cannot be found')
    times = [str(p.get('dueAt')) for p in li]
    dupes = sorted({t for t in times if times.count(t) > 1})
    if dupes:
        fail(f'two LinkedIn posts share a dueAt: {dupes}')

emit()
