#!/usr/bin/env python3
# provenance: shape `first-comment-link`, seen in 5 sessions (conservative count).
# Hard rules enforced: HR-3 (product site link only, never a code host or an install
# command), HR-1 (no em dashes, any encoding), HR-6 (the record stays scheduled).
"""Verifier for first-comment-link."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
URL = re.compile(r'https?://[^\s<>()\[\]"\',]+')
SITE = 'https://toolshelf.example/'
ENTITY_ID = 'urn:org:5512347'

ws = Path(sys.argv[1])
p = ws / 'queue' / 'scheduled-post.json'

# The record is loaded once, outside the sections: every section reads it, so each one
# has to be able to say for itself that there is nothing to read.
rec = None
load_problem = None
if not p.exists():
    load_problem = 'queue/scheduled-post.json missing'
else:
    raw = p.read_text(encoding='utf-8', errors='replace')
    try:
        parsed = json.loads(raw)
    except Exception as e:  # noqa: BLE001 - any parse failure is the same failure here
        load_problem = f'queue/scheduled-post.json is not valid JSON: {e}'
    else:
        if not isinstance(parsed, dict):
            load_problem = 'queue/scheduled-post.json must stay a single JSON object'
        else:
            rec = parsed

body = str(rec.get('body', '')) if rec else ''
fc = str(rec.get('firstComment') or '') if rec else ''

# Outcome: the prompt points at the queued record; leaving it unparseable is the
# corruption any careful agent avoids without being told.
with section('record-parses', 'outcome'):
    if load_problem:
        fail(load_problem)

# Outcome: the edit is to two fields of an existing record; dropping the other keys
# destroys the queued post rather than editing it.
with section('record-keys-kept', 'outcome'):
    if rec is None:
        fail(load_problem or 'no record to read keys from')
    for key in ('id', 'channel', 'dueAt', 'status', 'body', 'firstComment', 'mentions'):
        if key not in rec:
            fail(f'record lost key {key!r}; keys present: {sorted(rec)}')

# Outcome: "queued for tomorrow" is the prompt's own description of the state; a post
# that comes back unscheduled or re-dated was broken, not edited.
with section('schedule-untouched', 'outcome'):
    if rec is None:
        fail(load_problem or 'no record to check the schedule of')
    if rec.get('id') != 'p-8812' or rec.get('dueAt') != '2026-09-19T08:30:00Z':
        fail(f'id/dueAt were changed: id={rec.get("id")!r} dueAt={rec.get("dueAt")!r}')
    if str(rec.get('status')).lower() != 'scheduled':
        fail(f'status is {rec.get("status")!r}; the post was already scheduled and stays scheduled')

# Outcome: "make sure the download link is on the first comment" is the prompt, in
# those words.
with section('first-comment-has-link', 'outcome'):
    if rec is None:
        fail(load_problem or 'no record to read the first comment from')
    if not fc.strip():
        fail('firstComment is empty; the download link belongs there')
    if not URL.findall(fc):
        fail(f'firstComment carries no link: {fc[:120]!r}')

# Convention: HR-1. The prompt says nothing about punctuation and the seeded body ships
# with an em dash already in it.
with section('no-em-dash', 'convention'):
    if rec is None:
        fail(load_problem or 'no record to check for em dashes')
    for label, text in (('body', body), ('firstComment', fc)):
        m = DASH.search(text)
        if m:
            s = max(0, m.start() - 35)
            fail(f'em dash in {label}: ...{text[s:m.end() + 35]!r}')

# Convention: HR-3. The seeded body links repo.example, so moving that link answers the
# prompt literally; swapping it for the toolshelf product page is the house rule.
with section('first-comment-product-link', 'convention'):
    if rec is None:
        fail(load_problem or 'no record to read the first comment from')
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

# Outcome: if the link is to be on the first comment, it is no longer in the body; that
# is what the prompt asked for.
with section('body-link-moved', 'outcome'):
    if rec is None:
        fail(load_problem or 'no record to read the body from')
    body_urls = URL.findall(body)
    if body_urls:
        fail(f'post body still carries a link ({body_urls[0]!r}); the link lives in the first comment')

# Convention: HR-3. An install command is not a link, so the prompt does not reach it;
# only the house rule says it has to leave the body too.
with section('body-no-install-command', 'convention'):
    if rec is None:
        fail(load_problem or 'no record to read the body from')
    low_body = body.lower()
    for bad in ('npx ', 'repo.example', 'github.com'):
        if bad in low_body:
            fail(f'post body contains {bad!r}; no code host links, no install commands')

# Outcome: "tag Northpin on the post" is the prompt; a tag nobody can read is not a tag.
with section('body-mentions-northpin', 'outcome'):
    if rec is None:
        fail(load_problem or 'no record to read the body from')
    if 'northpin' not in body.lower():
        fail('post body never mentions Northpin; the readable @Northpin belongs in the body')

# Outcome: same prompt line, and partners.json in the seeded workspace gives Northpin's
# entityId next to the record's empty mentions array, so this is reachable without the skill.
with section('mentions-entity-id', 'outcome'):
    if rec is None:
        fail(load_problem or 'no record to read mentions from')
    mentions = rec.get('mentions')
    if not isinstance(mentions, list) or not mentions:
        fail('mentions is empty; a tag needs the partner entityId to notify anyone')
    blob = json.dumps(mentions)
    if ENTITY_ID not in blob:
        fail(f'mentions does not carry Northpin entityId {ENTITY_ID!r}: {blob[:160]}')

emit()
