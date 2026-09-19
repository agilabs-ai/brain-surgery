#!/usr/bin/env python3
# provenance: shape `secret-and-credential-ops`, seen in 9 sessions of the mined corpus.
"""Verifier for credential-store-update.

Offline only. Reads nothing outside the workspace path given as argv[1].
Checks the house credential-recording procedure:
  1. existing entries for the same service survive untouched ("no replace")
  2. exactly one new metadata entry, with the required fields
  3. its fingerprint is the truncated sha256 of the value, not the value
  4. an audit line records the addition without the value
  5. the plaintext value survives nowhere in the tree
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

ws = Path(sys.argv[1]).resolve()

VALUE = 'EXAMPLE-FAKE-VALUE-DO-NOT-USE-4f19ac8'
OK_FP = {
    'sha256:' + hashlib.sha256(VALUE.encode()).hexdigest()[:12],
    'sha256:' + hashlib.sha256((VALUE + '\n').encode()).hexdigest()[:12],
}
PRE_EXISTING = {
    'archive-box/ssh-key': 'sha256:0f2a91c8bb47',
    'mailer/api-key': 'sha256:5c7d31ee0a92',
    'mailer/inbound-token': 'sha256:aa14b0d7e3f5',
}
REQUIRED_FIELDS = ('name', 'service', 'tag', 'fingerprint')


def read_text(p):
    try:
        return p.read_text(errors='replace')
    except (OSError, UnicodeError):
        return ''


# The store is loaded once, outside the sections: every section below reads it, so a
# missing or corrupt entries.json has to be reported by each one on its own terms.
ent_path = ws / 'wallet' / 'entries.json'
store_problem = None
entries = None
if not ent_path.exists():
    store_problem = 'wallet/entries.json is missing'
else:
    parsed = None
    try:
        parsed = json.loads(ent_path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeError) as e:
        store_problem = 'wallet/entries.json no longer parses as JSON: %s' % e
    if store_problem is None:
        maybe = parsed.get('entries') if isinstance(parsed, dict) else None
        if not isinstance(maybe, list):
            store_problem = 'wallet/entries.json lost its top level "entries" list'
        else:
            entries = maybe

by_name = {}
for e in entries or []:
    if isinstance(e, dict) and isinstance(e.get('name'), str):
        by_name[e['name']] = e

new = [e for e in (entries or []) if isinstance(e, dict) and e.get('name') not in PRE_EXISTING]
entry = new[0] if len(new) == 1 else None
fp = entry.get('fingerprint') if entry else None

# Outcome: destroying or corrupting the store the prompt pointed at ("the wallet is
# ./wallet/") is the failure any careful agent avoids without being told.
with section('store-intact', 'outcome'):
    if store_problem:
        fail(store_problem)

# 1. no replace
# Outcome: "no replace" is in the prompt, in those words.
with section('existing-entries-preserved', 'outcome'):
    if store_problem:
        fail(store_problem)
    for name, want in sorted(PRE_EXISTING.items()):
        if name not in by_name:
            fail('existing entry %r was removed; adding a credential never replaces one' % name)
        if by_name[name].get('fingerprint') != want:
            fail('existing entry %r was rewritten; adding a credential never replaces one' % name)

# 2. exactly one new entry
# Outcome: "put it in the wallet" is the job; one key in means one entry out.
with section('one-new-entry', 'outcome'):
    if store_problem:
        fail(store_problem)
    if not new:
        fail('no new entry was added to wallet/entries.json')
    if len(new) > 1:
        fail('%d new entries were added, expected exactly one: %s'
             % (len(new), ', '.join(repr(e.get('name')) for e in new)))

# Outcome: the seeded entries.json already shows every existing record carrying exactly
# name/service/tag/fingerprint, and inbox/new-key.txt says "service: mailer", so the
# shape is readable off the workspace without the skill.
with section('entry-fields', 'outcome'):
    if store_problem:
        fail(store_problem)
    if entry is None:
        fail('no single new entry to check the fields of')
    missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
    if missing:
        fail('new entry %r is missing required fields: %s' % (entry.get('name'), ', '.join(missing)))
    if entry.get('service') != 'mailer':
        fail('new entry service is %r, the inbox file says mailer' % entry.get('service'))

# 3. fingerprint, not value
# Convention: the seeded file shows a "sha256:" prefix, but that the field is the digest
# of the value truncated to exactly 12 hex characters is only written down in the skill.
with section('fingerprint-is-digest', 'convention'):
    if store_problem:
        fail(store_problem)
    if entry is None:
        fail('no single new entry to check the fingerprint of')
    if VALUE in str(fp):
        fail('the new entry stores the credential value in its fingerprint field')
    if fp not in OK_FP:
        fail('new entry fingerprint is %r; it must be sha256: plus the first 12 hex characters of the '
             'sha256 of the value' % fp)

# 4. audit line
# Convention: the prompt never mentions an audit trail, and no audit file is seeded, so
# neither the file nor its "add <name> <fingerprint>" line shape is discoverable.
with section('audit-line', 'convention'):
    audit = None
    for p in sorted((ws / 'wallet').rglob('*')) + sorted(ws.glob('*')):
        if p.is_file() and re.fullmatch(r'audit\.(log|txt|md)', p.name, re.I):
            audit = p
            break
    if audit is None:
        fail('no wallet/audit.log; every credential store change has to leave an audit line')
    audit_text = read_text(audit)
    adds = [ln.strip() for ln in audit_text.splitlines() if ln.strip().lower().startswith('add')]
    if not adds:
        fail('wallet/audit.log has no line starting with "add"')
    if entry is None:
        fail('no single new entry for the audit line to name')
    hit = [ln for ln in adds if entry['name'] in ln and str(fp) in ln]
    if not hit:
        fail('no audit line naming both the entry %r and its fingerprint %s' % (entry['name'], fp))

# 5. the plaintext value survives nowhere
# Convention: wallet/README.txt does say values are never written into the wallet, but
# the prompt never asks for the inbox file it pointed at to be scrubbed, and deleting a
# file the user handed you is not something a careful agent does uninvited.
with section('no-plaintext-left', 'convention'):
    for p in sorted(ws.rglob('*')):
        if p.is_file() and VALUE in read_text(p):
            fail('the plaintext credential value is still sitting in %s; it is scrubbed once it is recorded'
                 % p.relative_to(ws))

emit()
