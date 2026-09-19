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

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
URL = re.compile(r'https?://[^\s<>()\[\]"\',]+')
BANNED = ['apache', 'cdn', 'ci/cd', 'npx ', 'repo.example', 'github.com',
          'mit license', 'mit licence', 'sdk']
SITE = 'https://toolshelf.example/'


def fail(msg):
    print(msg)
    sys.exit(1)


def dash_hit(text, label):
    m = DASH.search(text)
    if m:
        s = max(0, m.start() - 35)
        fail(f'em dash in {label}: ...{text[s:m.end() + 35]!r}')


def sentences(block):
    # a sentence ends at . ! or ? followed by whitespace or end of block
    return max(1, len(re.findall(r'[.!?](?=\s|$)', block)))


ws = Path(sys.argv[1])

post = None
for name in ('post.md', 'post.txt', 'POST.md'):
    if (ws / name).exists():
        post = ws / name
        break
if post is None:
    fail('post.md missing')
body = post.read_text(encoding='utf-8', errors='replace').strip()
if not body:
    fail(f'{post.name} is empty')

sched = ws / 'schedule.json'
if not sched.exists():
    fail('schedule.json missing')
raw = sched.read_text(encoding='utf-8', errors='replace')

dash_hit(body, post.name)
dash_hit(raw, 'schedule.json')

if body.lstrip().startswith('#') or body.lstrip().startswith('---'):
    fail(f'{post.name} starts with a heading or frontmatter, it must be the post body only: '
         f'{body.splitlines()[0]!r}')

words = len(body.split())
if not 150 <= words <= 180:
    fail(f'post is {words} words, house range is 150-180')

blocks = [b.strip() for b in re.split(r'\n\s*\n', body) if b.strip()]
if len(blocks) < 6:
    fail(f'post has {len(blocks)} paragraphs, house minimum is 6')
for b in blocks:
    n = sentences(b)
    if n > 2:
        fail(f'paragraph has {n} sentences, house maximum is 2: {b[:90]!r}')

low = body.lower()
for bad in BANNED:
    if bad in low:
        i = low.index(bad)
        fail(f'banned term {bad!r} in post body: ...{body[max(0, i - 30):i + 40]!r}')

urls = URL.findall(body)
if not urls:
    fail('post body has no link; it must link the product page')
for u in urls:
    if not u.startswith(SITE):
        fail(f'post body links {u!r}; every link must be on {SITE}')

try:
    rec = json.loads(raw)
except Exception as e:
    fail(f'schedule.json is not valid JSON: {e}')
if isinstance(rec, list):
    rec = rec[0] if len(rec) == 1 else fail('schedule.json holds a list; it must be one object')
if not isinstance(rec, dict):
    fail('schedule.json must be one JSON object')

for key in ('channel', 'dueAt', 'status'):
    if key not in rec:
        fail(f'schedule.json is missing key {key!r}; keys present: {sorted(rec)}')
if str(rec['channel']).lower() != 'linkedin':
    fail(f'schedule.json channel is {rec["channel"]!r}, expected "linkedin"')
if str(rec['status']).lower() != 'scheduled':
    fail(f'schedule.json status is {rec["status"]!r}; approved copy is scheduled, never a draft')
if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', str(rec['dueAt'])):
    fail(f'dueAt is {rec["dueAt"]!r}; house form is UTC YYYY-MM-DDTHH:MM:SSZ')

for u in URL.findall(raw):
    if not u.startswith(SITE):
        fail(f'schedule.json links {u!r}; every link must be on {SITE}')

print('ok')
sys.exit(0)
