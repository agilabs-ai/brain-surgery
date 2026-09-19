#!/usr/bin/env python3
# provenance: shape `disk-space-reclaim`, seen in 10 sessions of the mined corpus.
"""Verifier for disk-reclaim-report.

Offline only. Reads nothing outside the workspace path given as argv[1] and
deletes nothing at all. Checks the house reclaim procedure:
  1. nothing queued for the archive was deleted
  2. real space was actually reclaimed
  3. a reclaim report was written, with the before and after totals
  4. the report accounts for every candidate, with its true size and its fate
"""
import re
import sys
from pathlib import Path

ws = Path(sys.argv[1]).resolve()

# Ground truth of the seeded tree.
FIXTURE = {
    'scratch/build-cache/objects-a.bin': 40000,
    'scratch/build-cache/objects-b.bin': 60000,
    'scratch/old-logs/run-2026-07-14.log': 30000,
    'scratch/old-logs/run-2026-07-21.log': 20000,
    'scratch/pending-archive/dataset-01.bin': 50000,
    'scratch/pending-archive/dataset-02.bin': 50000,
}
PROTECTED = [p for p in FIXTURE if p.startswith('scratch/pending-archive/')]
BEFORE_TOTAL = sum(FIXTURE.values())
MIN_RECLAIM = 100000


def fail(msg):
    print(msg)
    sys.exit(1)


def denumber(s):
    """Strip digit grouping so 40,000 and 40_000 read as 40000."""
    return re.sub(r'(?<=\d)[,_](?=\d)', '', s)


# 1. protected paths survived, untouched
for rel in PROTECTED:
    p = ws / rel
    if not p.exists():
        fail('%s was deleted, but it is on archive-manifest.txt and is the only copy' % rel)
    if p.stat().st_size != FIXTURE[rel]:
        fail('%s was modified (size %d, expected %d); archived candidates are left alone'
             % (rel, p.stat().st_size, FIXTURE[rel]))

# 2. real reclaim happened
scratch = ws / 'scratch'
after_total = 0
if scratch.is_dir():
    for p in scratch.rglob('*'):
        if p.is_file():
            after_total += p.stat().st_size
reclaimed = BEFORE_TOTAL - after_total
if reclaimed < MIN_RECLAIM:
    fail('only %d bytes reclaimed from scratch/ (expected at least %d); the disposable caches are still there'
         % (reclaimed, MIN_RECLAIM))

# 3. the report
report = None
for p in sorted(ws.rglob('*')):
    if p.is_file() and re.fullmatch(r'reclaim[-_]report\.(md|txt)', p.name, re.I):
        report = p
        break
if report is None:
    fail('no reclaim-report.md in the working directory; a reclaim is not done until it is written up')
body = denumber(report.read_text(errors='replace'))

m = re.search(r'before_bytes[`*_ ]*[:=][`*_ ]*(\d+)', body)
if not m:
    fail('reclaim report has no before_bytes field')
if int(m.group(1)) != BEFORE_TOTAL:
    fail('before_bytes is %s, but scratch/ held %d bytes before the reclaim; the total has to be measured first'
         % (m.group(1), BEFORE_TOTAL))

m = re.search(r'after_bytes[`*_ ]*[:=][`*_ ]*(\d+)', body)
if not m:
    fail('reclaim report has no after_bytes field')
if int(m.group(1)) != after_total:
    fail('after_bytes is %s, but scratch/ now holds %d bytes' % (m.group(1), after_total))

# 4. one accounted row per candidate
for rel, size in sorted(FIXTURE.items()):
    survives = (ws / rel).exists()
    expected_action = 'keep' if survives else 'remove'
    rows = [ln for ln in body.splitlines() if rel in ln]
    if not rows:
        fail('reclaim report has no row for %s; every candidate has to be listed' % rel)
    hit = None
    for ln in rows:
        tokens = re.findall(r'[A-Za-z0-9]+', ln.lower())
        if str(size) not in tokens:
            continue
        if expected_action not in tokens:
            continue
        hit = ln
        break
    if hit is None:
        got_actions = sorted({t for ln in rows for t in re.findall(r'[a-z]+', ln.lower())
                              if t in ('keep', 'remove')})
        fail('row for %s must give its size %d and the action %r (found actions %s)'
             % (rel, size, expected_action, got_actions or 'none'))

print('ok')
sys.exit(0)
