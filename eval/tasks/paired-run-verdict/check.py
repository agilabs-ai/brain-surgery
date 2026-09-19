#!/usr/bin/env python3
# provenance: shape `eval-run-and-publish`, seen in 9 sessions (conservative count).
"""Verifier for paired-run-verdict.

Checks the house verdict schema, the rule that a non zero exit run is excluded
from its arm's mean, and that the headline reaches the page in the house shape.
Ground truth is computed by hand from the seeded runs/ files:

    with:    90, 84, 92, (exit 1), 86, 88   -> mean 88.0 over n=5
    without: 60, 54, (exit 1), 58, 62, 56   -> mean 58.0 over n=5

Standard library only.
"""
import json
import re
import sys
from pathlib import Path

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)

WANT = {
    'winner_arm': 'with',
    'margin': 30.0,
    'samples': 6,
    'excluded': 2,
    'arms': {'with': {'mean': 88.0, 'n': 5}, 'without': {'mean': 58.0, 'n': 5}},
}
HEADLINE = '88.0 vs 58.0'


def fail(msg):
    print(msg)
    sys.exit(1)


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


ws = Path(sys.argv[1])
vf = ws / 'verdict.json'
if not vf.exists():
    fail('verdict.json missing from the workspace')
try:
    got = json.loads(vf.read_text(encoding='utf-8'))
except json.JSONDecodeError as e:
    fail(f'verdict.json is not valid JSON: {e}')
if not isinstance(got, dict):
    fail(f'verdict.json holds a {type(got).__name__}, expected an object')

extra = sorted(set(got) - set(WANT))
missing = sorted(set(WANT) - set(got))
if missing:
    fail(f'verdict.json is missing key(s) {missing}')
if extra:
    fail(f'verdict.json has unexpected top level key(s) {extra}; the schema is '
         f'{sorted(WANT)} and nothing else')

if got['winner_arm'] != WANT['winner_arm']:
    fail(f'winner_arm is {got["winner_arm"]!r}, expected {WANT["winner_arm"]!r}')
for k in ('samples', 'excluded'):
    if got[k] != WANT[k]:
        fail(f'{k} is {got[k]!r}, expected {WANT[k]} '
             f'(samples counts runs per arm, excluded counts non zero exit runs)')
if not num(got['margin']) or round(float(got['margin']), 1) != WANT['margin']:
    fail(f'margin is {got["margin"]!r}, expected {WANT["margin"]} '
         f'(winner mean minus loser mean, one decimal)')

arms = got['arms']
if not isinstance(arms, dict) or sorted(arms) != ['with', 'without']:
    fail(f'arms must be an object keyed "with" and "without", got {arms!r}')
for name, want_arm in WANT['arms'].items():
    a = arms[name]
    if not isinstance(a, dict) or sorted(a) != ['mean', 'n']:
        fail(f'arms.{name} must hold exactly mean and n, got {a!r}')
    if not num(a['mean']) or round(float(a['mean']), 1) != want_arm['mean']:
        fail(f'arms.{name}.mean is {a["mean"]!r}, expected {want_arm["mean"]} '
             f'(runs with a non zero exit are excluded from the mean)')
    if a['n'] != want_arm['n']:
        fail(f'arms.{name}.n is {a["n"]!r}, expected {want_arm["n"]} '
             f'(runs that counted toward the mean)')

page = ws / 'page' / 'index.html'
if not page.exists():
    fail('page/index.html missing from the workspace')
html = page.read_text(encoding='utf-8', errors='replace')
m = EMDASH.search(html)
if m:
    line_no = html[:m.start()].count('\n') + 1
    fail(f'em dash in page/index.html at line {line_no}')
if HEADLINE not in html:
    fail(f'page/index.html does not carry the headline {HEADLINE!r} '
         f'(winner mean, " vs ", loser mean, one decimal each)')
if 'pending' in html:
    fail('page/index.html still carries the "pending" placeholder')

print('ok')
sys.exit(0)
