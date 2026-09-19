#!/usr/bin/env python3
# provenance: shape `li-post-draft-and-schedule`, seen in 12 sessions (conservative count).
# Hard rules enforced: HR-1 (no em dashes, any encoding), HR-3 (product site link only,
# no licence/infra vocabulary), HR-4 (150-180 words, many short paragraphs), HR-6
# (a confirmed post is scheduled, never parked as a draft).
"""Verifier for post-draft-and-schedule."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
URL = re.compile(r'https?://[^\s<>()\[\]"\',]+')
BANNED = ['apache', 'cdn', 'ci/cd', 'npx ', 'repo.example', 'github.com',
          'mit license', 'mit licence', 'sdk']
SITE = 'https://toolshelf.example/'


def dash_hit(text, label):
    m = DASH.search(text)
    if m:
        s = max(0, m.start() - 35)
        fail(f'em dash in {label}: ...{text[s:m.end() + 35]!r}')


def sentences(block):
    # a sentence ends at . ! or ? followed by whitespace or end of block
    return max(1, len(re.findall(r'[.!?](?=\s|$)', block)))


ws = Path(sys.argv[1])

# Both deliverables are read and parsed once, outside the sections, so a missing
# or malformed file fails every check that needs it with its own message rather
# than letting later checks run on nothing.
post = None
for name in ('post.md', 'post.txt', 'POST.md'):
    if (ws / name).exists():
        post = ws / name
        break
body = post.read_text(encoding='utf-8', errors='replace').strip() if post else ''

sched = ws / 'schedule.json'
raw = sched.read_text(encoding='utf-8', errors='replace') if sched.exists() else ''

rec = None
sched_error = None
if not sched.exists():
    sched_error = 'schedule.json missing'
else:
    try:
        parsed = json.loads(raw)
    except Exception as e:
        sched_error = f'schedule.json is not valid JSON: {e}'
    else:
        if isinstance(parsed, list):
            if len(parsed) == 1:
                parsed = parsed[0]
            else:
                sched_error = 'schedule.json holds a list; it must be one object'
        if sched_error is None:
            if isinstance(parsed, dict):
                rec = parsed
            else:
                sched_error = 'schedule.json must be one JSON object'

# Outcome: the prompt says write the LinkedIn post into post.md, by name.
with section('post-written', 'outcome'):
    if post is None:
        fail('post.md missing')
    if not body:
        fail(f'{post.name} is empty')

# Outcome: the prompt says put the scheduling details in schedule.json, by name,
# and a file that does not parse is not a record anyone can read.
with section('schedule-written', 'outcome'):
    if sched_error:
        fail(sched_error)

# Convention: HR-1. The prompt says nothing about punctuation, and the seeded
# release note the copy is drawn from is full of em dashes.
with section('no-em-dash', 'convention'):
    if not body and sched_error:
        fail('neither deliverable exists, so nothing could be checked for em dashes')
    if body:
        dash_hit(body, post.name)
    if raw:
        dash_hit(raw, 'schedule.json')

# Convention: "post.md holds the post body and nothing else" is a house file
# rule; the prompt just says write the post into it.
with section('post-body-only', 'convention'):
    if not body:
        fail('no post body to check')
    if body.lstrip().startswith('#') or body.lstrip().startswith('---'):
        fail(f'{post.name} starts with a heading or frontmatter, it must be the post body only: '
             f'{body.splitlines()[0]!r}')

# Convention: HR-4. The 150-180 word range is a house number the prompt never
# states; nothing in the request implies any particular length.
with section('post-length', 'convention'):
    if not body:
        fail('no post body to measure')
    words = len(body.split())
    if not 150 <= words <= 180:
        fail(f'post is {words} words, house range is 150-180')

# Convention: HR-4 again, the house paragraph shape (at least six blocks, at
# most two sentences each). Pure local format.
with section('post-paragraph-shape', 'convention'):
    if not body:
        fail('no post body to check the paragraph shape of')
    blocks = [b.strip() for b in re.split(r'\n\s*\n', body) if b.strip()]
    if len(blocks) < 6:
        fail(f'post has {len(blocks)} paragraphs, house minimum is 6')
    for b in blocks:
        n = sentences(b)
        if n > 2:
            fail(f'paragraph has {n} sentences, house maximum is 2: {b[:90]!r}')

# Convention: HR-3. The banned vocabulary sits in the seeded release note as
# perfectly quotable material, and the prompt never warns anyone off it.
with section('no-infra-vocabulary', 'convention'):
    if not body:
        fail('no post body to check for banned terms')
    low = body.lower()
    for bad in BANNED:
        if bad in low:
            i = low.index(bad)
            fail(f'banned term {bad!r} in post body: ...{body[max(0, i - 30):i + 40]!r}')

# Convention: HR-3. The prompt never asks for a link at all, let alone that
# every link be on the product site rather than the repo host.
with section('product-link-only', 'convention'):
    if not body and not raw:
        fail('nothing was written, so no links could be checked')
    if body:
        urls = URL.findall(body)
        if not urls:
            fail('post body has no link; it must link the product page')
        for u in urls:
            if not u.startswith(SITE):
                fail(f'post body links {u!r}; every link must be on {SITE}')
    for u in URL.findall(raw):
        if not u.startswith(SITE):
            fail(f'schedule.json links {u!r}; every link must be on {SITE}')

# Convention: the exact field names channel, dueAt and status are the house
# record shape; the prompt only says "the scheduling details".
with section('schedule-fields-present', 'convention'):
    if rec is None:
        fail(sched_error or 'no schedule.json object to check the fields of')
    for key in ('channel', 'dueAt', 'status'):
        if key not in rec:
            fail(f'schedule.json is missing key {key!r}; keys present: {sorted(rec)}')

# Outcome: the prompt says write the LinkedIn post, so the channel it is queued
# on is stated in the request.
with section('scheduled-for-linkedin', 'outcome'):
    if rec is None:
        fail(sched_error or 'no schedule.json object to read the channel from')
    if 'channel' not in rec:
        fail(f'schedule.json records no channel; keys present: {sorted(rec)}')
    if str(rec['channel']).lower() != 'linkedin':
        fail(f'schedule.json channel is {rec["channel"]!r}, expected "linkedin"')

# Convention: HR-6. The prompt does say "get it queued", but the check demands
# the fixed house word "scheduled"; that vocabulary is skill-only.
with section('status-scheduled', 'convention'):
    if rec is None:
        fail(sched_error or 'no schedule.json object to read the status from')
    if 'status' not in rec:
        fail(f'schedule.json records no status; keys present: {sorted(rec)}')
    if str(rec['status']).lower() != 'scheduled':
        fail(f'schedule.json status is {rec["status"]!r}; approved copy is scheduled, '
             f'never a draft')

# Convention: the exact UTC timestamp format string is a house form. The prompt
# says "tomorrow" and says nothing about how to write it down.
with section('due-at-format', 'convention'):
    if rec is None:
        fail(sched_error or 'no schedule.json object to read dueAt from')
    if 'dueAt' not in rec:
        fail(f'schedule.json records no dueAt; keys present: {sorted(rec)}')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', str(rec['dueAt'])):
        fail(f'dueAt is {rec["dueAt"]!r}; house form is UTC YYYY-MM-DDTHH:MM:SSZ')

emit()
