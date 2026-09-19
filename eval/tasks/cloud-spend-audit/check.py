#!/usr/bin/env python3
# provenance: shape `cloud-cost-audit`, seen in 7 sessions of the mined corpus.
"""Verifier for cloud-spend-audit.

Offline only. Reads nothing outside the workspace path given as argv[1].
Checks the house spend-audit conventions:
  1. one row per account in the latest month, including the one that nets to zero
  2. every total exact to the cent, credits included
  3. the account's largest positive line named as the driver
  4. an action from the closed vocabulary
  5. plain numbers, no currency symbols
  6. no em dashes (house rule, any encoding)
"""
import re
import sys
from pathlib import Path

ws = Path(sys.argv[1]).resolve()

# Ground truth, derived by hand from the seeded export for month 2026-09.
EXPECTED = {
    'acct-blue': ('450.07', 'compute'),
    'acct-green': ('0.00', 'managed-db'),
    'acct-slate': ('238.10', 'inference-api'),
}
GRAND_TOTAL = '688.17'
ACTIONS = ('keep', 'cap', 'migrate', 'stop')
DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)


def fail(msg):
    print(msg)
    sys.exit(1)


report = None
for p in sorted(ws.rglob('*')):
    if p.is_file() and re.fullmatch(r'spend[-_]audit\.(md|txt)', p.name, re.I):
        report = p
        break
if report is None:
    fail('spend-audit.md was not written')
body = report.read_text(errors='replace')

m = DASH.search(body)
if m:
    line = body[:m.start()].count('\n') + 1
    fail('em dash at line %d: %r' % (line, body.splitlines()[line - 1].strip()[:80]))

for sym in ('€', '$', '£'):
    if sym in body:
        fail('currency symbol %r in the audit; amounts are written as plain numbers' % sym)


def has_amount(text, amount):
    return re.search(r'(?<![\d.])' + re.escape(amount) + r'(?![\d])', text) is not None


def has_driver(text, driver):
    """Tolerate managed_db or "managed db" for managed-db."""
    pat = r'[-_ ]'.join(re.escape(part) for part in driver.split('-'))
    return re.search(pat, text, re.I) is not None


for acct, (total, driver) in sorted(EXPECTED.items()):
    rows = [ln for ln in body.splitlines() if acct in ln]
    if not rows:
        fail('no row for %s; every account in the latest month gets a row, including a netted out one' % acct)
    problem = 'row for %s is incomplete' % acct
    ok = False
    for ln in rows:
        if not has_amount(ln, total):
            problem = ('row for %s does not carry its exact total %s (credits count toward the total): %r'
                       % (acct, total, ln.strip()[:100]))
            continue
        if not has_driver(ln, driver):
            problem = ('row for %s does not name %s as the driver, which is its largest line: %r'
                       % (acct, driver, ln.strip()[:100]))
            continue
        tokens = re.findall(r'[a-z]+', ln.lower())
        if not any(a in tokens for a in ACTIONS):
            problem = ('row for %s has no action from keep, cap, migrate, stop: %r'
                       % (acct, ln.strip()[:100]))
            continue
        ok = True
        break
    if not ok:
        fail(problem)

m = re.search(r'total_eur[`*_ ]*[:=][`*_ ]*(-?[\d,_]+\.\d\d)', body)
if not m:
    fail('no total_eur field with the all-account total')
if re.sub(r'(?<=\d)[,_](?=\d)', '', m.group(1)) != GRAND_TOTAL:
    fail('total_eur is %s, the latest month sums to %s' % (m.group(1), GRAND_TOTAL))

print('ok')
sys.exit(0)
