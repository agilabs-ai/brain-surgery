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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

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


def has_amount(text, amount):
    return re.search(r'(?<![\d.])' + re.escape(amount) + r'(?![\d])', text) is not None


def has_driver(text, driver):
    """Tolerate managed_db or "managed db" for managed-db."""
    pat = r'[-_ ]'.join(re.escape(part) for part in driver.split('-'))
    return re.search(pat, text, re.I) is not None


def rows_for(body, acct):
    return [ln for ln in body.splitlines() if acct in ln]


# The audit file is located once, outside the sections, because every section
# below reads it and each one has to say for itself that it is missing.
doc = None
for p in sorted(ws.rglob('*')):
    if p.is_file() and re.fullmatch(r'spend[-_]audit\.(md|txt)', p.name, re.I):
        doc = p
        break
body = doc.read_text(errors='replace') if doc else ''

# Outcome: the prompt says "write it up in spend-audit.md here", filename included.
with section('audit-written', 'outcome'):
    if doc is None:
        fail('spend-audit.md was not written')

# Convention: no em dashes is a house writing rule; the prompt says nothing about punctuation.
with section('no-em-dash', 'convention'):
    if doc is None:
        fail('no spend audit to check for em dashes')
    m = DASH.search(body)
    if m:
        line = body[:m.start()].count('\n') + 1
        fail('em dash at line %d: %r' % (line, body.splitlines()[line - 1].strip()[:80]))

# Convention: "amounts are written as plain numbers" is a house format rule the prompt never states.
with section('plain-numbers', 'convention'):
    if doc is None:
        fail('no spend audit to check for currency symbols')
    for sym in ('€', '$', '£'):
        if sym in body:
            fail('currency symbol %r in the audit; amounts are written as plain numbers' % sym)

# Outcome: the prompt asks for it "broken down per account", and the account that nets
# to zero is still an account in the latest month.
with section('row-per-account', 'outcome'):
    if doc is None:
        fail('no spend audit to read account rows from')
    for acct in sorted(EXPECTED):
        if not rows_for(body, acct):
            fail('no row for %s; every account in the latest month gets a row, including a netted out one' % acct)

# Outcome: a wrong total is a wrong answer; the credit lines are the arithmetic the prompt asked for.
with section('account-totals-exact', 'outcome'):
    if doc is None:
        fail('no spend audit to read account totals from')
    for acct, (total, _driver) in sorted(EXPECTED.items()):
        rows = rows_for(body, acct)
        if not rows:
            fail('no row for %s; every account in the latest month gets a row, including a netted out one' % acct)
        if not any(has_amount(ln, total) for ln in rows):
            fail('row for %s does not carry its exact total %s (credits count toward the total): %r'
                 % (acct, total, rows[0].strip()[:100]))

# Outcome: "what is driving each one" is the prompt, in those words.
with section('drivers-named', 'outcome'):
    if doc is None:
        fail('no spend audit to read drivers from')
    for acct, (_total, driver) in sorted(EXPECTED.items()):
        rows = rows_for(body, acct)
        if not rows:
            fail('no row for %s; every account in the latest month gets a row, including a netted out one' % acct)
        if not any(has_driver(ln, driver) for ln in rows):
            fail('row for %s does not name %s as the driver, which is its largest line: %r'
                 % (acct, driver, rows[0].strip()[:100]))

# Convention: the prompt asks "what we do about it", but keep/cap/migrate/stop is a closed
# house vocabulary; any sensible recommendation in other words answers the prompt.
with section('action-from-vocabulary', 'convention'):
    if doc is None:
        fail('no spend audit to read actions from')
    for acct in sorted(EXPECTED):
        rows = rows_for(body, acct)
        if not rows:
            fail('no row for %s; every account in the latest month gets a row, including a netted out one' % acct)
        ok = False
        for ln in rows:
            tokens = re.findall(r'[a-z]+', ln.lower())
            if any(a in tokens for a in ACTIONS):
                ok = True
                break
        if not ok:
            fail('row for %s has no action from keep, cap, migrate, stop: %r'
                 % (acct, rows[0].strip()[:100]))

# Convention: the field name total_eur, and an all-account total at all, appear nowhere in
# the prompt, which asks only for a per-account breakdown.
with section('total-eur-field', 'convention'):
    if doc is None:
        fail('no spend audit to read total_eur from')
    m = re.search(r'total_eur[`*_ ]*[:=][`*_ ]*(-?[\d,_]+\.\d\d)', body)
    if not m:
        fail('no total_eur field with the all-account total')
    if re.sub(r'(?<=\d)[,_](?=\d)', '', m.group(1)) != GRAND_TOTAL:
        fail('total_eur is %s, the latest month sums to %s' % (m.group(1), GRAND_TOTAL))

emit()
