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


def fail(msg):
    print(msg)
    sys.exit(1)


def read_text(p):
    try:
        return p.read_text(errors='replace')
    except (OSError, UnicodeError):
        return ''


ent_path = ws / 'wallet' / 'entries.json'
if not ent_path.exists():
    fail('wallet/entries.json is missing')
try:
    doc = json.loads(ent_path.read_text())
except json.JSONDecodeError as e:
    fail('wallet/entries.json no longer parses as JSON: %s' % e)
entries = doc.get('entries') if isinstance(doc, dict) else None
if not isinstance(entries, list):
    fail('wallet/entries.json lost its top level "entries" list')

by_name = {}
for e in entries:
    if isinstance(e, dict) and isinstance(e.get('name'), str):
        by_name[e['name']] = e

# 1. no replace
for name, fp in sorted(PRE_EXISTING.items()):
    if name not in by_name:
        fail('existing entry %r was removed; adding a credential never replaces one' % name)
    if by_name[name].get('fingerprint') != fp:
        fail('existing entry %r was rewritten; adding a credential never replaces one' % name)

# 2. exactly one new entry
new = [e for e in entries if isinstance(e, dict) and e.get('name') not in PRE_EXISTING]
if not new:
    fail('no new entry was added to wallet/entries.json')
if len(new) > 1:
    fail('%d new entries were added, expected exactly one: %s'
         % (len(new), ', '.join(repr(e.get('name')) for e in new)))
entry = new[0]

missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
if missing:
    fail('new entry %r is missing required fields: %s' % (entry.get('name'), ', '.join(missing)))
if entry.get('service') != 'mailer':
    fail('new entry service is %r, the inbox file says mailer' % entry.get('service'))

# 3. fingerprint, not value
fp = entry.get('fingerprint')
if VALUE in str(fp):
    fail('the new entry stores the credential value in its fingerprint field')
if fp not in OK_FP:
    fail('new entry fingerprint is %r; it must be sha256: plus the first 12 hex characters of the '
         'sha256 of the value' % fp)

# 4. audit line
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
hit = [ln for ln in adds if entry['name'] in ln and fp in ln]
if not hit:
    fail('no audit line naming both the entry %r and its fingerprint %s' % (entry['name'], fp))

# 5. the plaintext value survives nowhere
for p in sorted(ws.rglob('*')):
    if p.is_file() and VALUE in read_text(p):
        fail('the plaintext credential value is still sitting in %s; it is scrubbed once it is recorded'
             % p.relative_to(ws))

print('ok')
sys.exit(0)
