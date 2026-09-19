#!/usr/bin/env python3
# provenance: shape `auth-token-sync`, seen in 7 sessions of the mined corpus.
"""Verifier for token-sync-across-hosts.

Offline only. Reads and writes nothing outside the workspace path given as argv[1].
Checks the house credential-handoff procedure:
  1. the token landed on the target host config
  2. the target file is mode 0600
  3. the origin copy is untouched
  4. a handoff log line was recorded in the house format
  5. no token value leaked into any other file
"""
import json
import os
import re
import stat
import sys
from pathlib import Path

ws = Path(sys.argv[1]).resolve()

ORIGIN = ws / 'origin' / 'agent-auth.json'
TARGET_DIR = ws / 'hosts' / 'relay-two' / 'config'
ACCESS = 'PLACEHOLDER-ACCESS-TOKEN-a1b2c3d4e5f6'
REFRESH = 'PLACEHOLDER-REFRESH-TOKEN-9z8y7x6w5v'
EXPECT_KEYS = ['accessToken', 'expiresAt', 'refreshToken', 'scopes']
ORIGIN_BYTES = (
    b'{\n  "accessToken": "PLACEHOLDER-ACCESS-TOKEN-a1b2c3d4e5f6",\n'
    b'  "refreshToken": "PLACEHOLDER-REFRESH-TOKEN-9z8y7x6w5v",\n'
    b'  "expiresAt": 1790000000,\n'
    b'  "scopes": ["read", "write"]\n}\n'
)


def fail(msg):
    print(msg)
    sys.exit(1)


def read_text(p):
    try:
        return p.read_text(errors='replace')
    except (OSError, UnicodeError):
        return ''


if not ORIGIN.exists():
    fail('origin/agent-auth.json is gone; the origin copy must be left in place')
if ORIGIN.read_bytes() != ORIGIN_BYTES:
    fail('origin/agent-auth.json was modified; the origin copy must stay byte-identical')

if not TARGET_DIR.is_dir():
    fail('hosts/relay-two/config/ is missing')

# 1. the token reached the target host
candidates = []
for p in sorted(TARGET_DIR.rglob('*')):
    if p.is_file() and ACCESS in read_text(p):
        candidates.append(p)
if not candidates:
    fail('no file under hosts/relay-two/config/ carries the access token; the token never reached the target host')
if len(candidates) > 1:
    fail('the token was written to %d files under hosts/relay-two/config/: %s'
         % (len(candidates), ', '.join(str(c.relative_to(ws)) for c in candidates)))
target = candidates[0]

try:
    parsed = json.loads(target.read_text())
except json.JSONDecodeError as e:
    fail('%s is not valid JSON: %s' % (target.relative_to(ws), e))
missing = [k for k in EXPECT_KEYS if k not in parsed]
if missing:
    fail('%s is missing credential keys: %s' % (target.relative_to(ws), ', '.join(missing)))
if parsed.get('refreshToken') != REFRESH:
    fail('%s does not carry the refresh token from the origin copy' % target.relative_to(ws))

# 2. mode 0600
mode = stat.S_IMODE(os.stat(target).st_mode)
if mode != 0o600:
    fail('%s has mode %04o; a credential file on a target host must be 0600' % (target.relative_to(ws), mode))

# 3. the handoff log
log = None
for p in sorted(ws.iterdir()):
    if p.is_file() and re.fullmatch(r'handoff[-_]log\.(txt|md|log)', p.name, re.I):
        log = p
        break
if log is None:
    fail('no handoff-log.txt in the working directory; every credential handoff has to be recorded')

log_text = read_text(log)
sync_lines = [ln.strip() for ln in log_text.splitlines() if ln.strip().lower().startswith('sync')]
if not sync_lines:
    fail('handoff log has no line starting with "sync"')

reason = None
for ln in sync_lines:
    if 'agent-auth.json' not in ln:
        reason = 'log line does not name the credential file: %r' % ln
        continue
    if '->' not in ln:
        reason = 'log line has no "->" between source and target: %r' % ln
        continue
    if 'hosts/relay-two/config' not in ln:
        reason = 'log line does not name the target path: %r' % ln
        continue
    m = re.search(r'keys=([A-Za-z0-9_,]+)', ln)
    if not m:
        reason = 'log line has no keys= field: %r' % ln
        continue
    got = sorted(k for k in m.group(1).split(',') if k)
    if got != EXPECT_KEYS:
        reason = 'log line keys=%s should list the credential keys %s' % (m.group(1), ','.join(EXPECT_KEYS))
        continue
    if not re.search(r'mode=0600\b', ln):
        reason = 'log line has no mode=0600 field: %r' % ln
        continue
    reason = None
    break
if reason:
    fail(reason)

# 4. no value leaked anywhere else
allowed = {ORIGIN.resolve(), target.resolve()}
for p in sorted(ws.rglob('*')):
    if not p.is_file() or p.resolve() in allowed:
        continue
    body = read_text(p)
    for secret, label in ((ACCESS, 'access token'), (REFRESH, 'refresh token')):
        if secret in body:
            fail('the %s value was written into %s; a credential value never leaves the credential file'
                 % (label, p.relative_to(ws)))

print('ok')
sys.exit(0)
