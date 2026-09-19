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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

EMDASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)

WANT = {
    'winner_arm': 'with',
    'margin': 30.0,
    'samples': 6,
    'excluded': 2,
    'arms': {'with': {'mean': 88.0, 'n': 5}, 'without': {'mean': 58.0, 'n': 5}},
}
HEADLINE = '88.0 vs 58.0'


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


ws = Path(sys.argv[1])
vf = ws / 'verdict.json'

# The verdict is parsed once, outside the sections: every later check reads it,
# and a missing or broken file has to fail each of them explicitly instead of
# letting them run on nothing.
got = None
verdict_error = None
if not vf.exists():
    verdict_error = 'verdict.json missing from the workspace'
else:
    try:
        parsed = json.loads(vf.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        verdict_error = f'verdict.json is not valid JSON: {e}'
    else:
        if isinstance(parsed, dict):
            got = parsed
        else:
            verdict_error = (f'verdict.json holds a {type(parsed).__name__}, '
                             f'expected an object')
arms = got.get('arms') if got is not None else None

# Outcome: the prompt says roll the paired run up into verdict.json, so the file
# existing and holding parseable JSON is the request in its own words.
with section('verdict-file-written', 'outcome'):
    if verdict_error:
        fail(verdict_error)

# Convention: the exact top level key set is the house schema. The prompt asks
# for a roll up and never names a single field.
with section('verdict-schema-keys', 'convention'):
    if got is None:
        fail(verdict_error or 'no verdict.json object to check the schema of')
    extra = sorted(set(got) - set(WANT))
    missing = sorted(set(WANT) - set(got))
    if missing:
        fail(f'verdict.json is missing key(s) {missing}')
    if extra:
        fail(f'verdict.json has unexpected top level key(s) {extra}; the schema is '
             f'{sorted(WANT)} and nothing else')

# Outcome: which arm won is the finding the paired run exists to produce, and it
# is readable straight off the seeded runs/ files.
with section('winner-arm-correct', 'outcome'):
    if got is None:
        fail(verdict_error or 'no verdict.json object to read the winner from')
    if 'winner_arm' not in got:
        fail('verdict.json records no winning arm')
    if got['winner_arm'] != WANT['winner_arm']:
        fail(f'winner_arm is {got["winner_arm"]!r}, expected {WANT["winner_arm"]!r}')

# Convention: what these two fields count is a house definition (samples is per
# arm, not the total), so the numbers are only right if you know the rule.
with section('sample-and-exclusion-counts', 'convention'):
    if got is None:
        fail(verdict_error or 'no verdict.json object to read the counts from')
    for k in ('samples', 'excluded'):
        if k not in got:
            fail(f'verdict.json is missing key {k!r}')
        if got[k] != WANT[k]:
            fail(f'{k} is {got[k]!r}, expected {WANT[k]} '
                 f'(samples counts runs per arm, excluded counts non zero exit runs)')

# Outcome: the margin is arithmetic over the seeded scores, a correct number.
with section('margin-correct', 'outcome'):
    if got is None:
        fail(verdict_error or 'no verdict.json object to read the margin from')
    if 'margin' not in got:
        fail('verdict.json records no margin between the arms')
    if not num(got['margin']) or round(float(got['margin']), 1) != WANT['margin']:
        fail(f'margin is {got["margin"]!r}, expected {WANT["margin"]} '
             f'(winner mean minus loser mean, one decimal)')

# Convention: the nesting, the arm key names and "exactly mean and n, nothing
# else" are the house schema again, not anything the prompt asks for.
with section('arms-shape', 'convention'):
    if got is None:
        fail(verdict_error or 'no verdict.json object to check the arms of')
    if not isinstance(arms, dict) or sorted(arms) != ['with', 'without']:
        fail(f'arms must be an object keyed "with" and "without", got {arms!r}')
    for name in WANT['arms']:
        a = arms[name]
        if not isinstance(a, dict) or sorted(a) != ['mean', 'n']:
            fail(f'arms.{name} must hold exactly mean and n, got {a!r}')

# Outcome: the per arm means are the headline numbers, and dropping a run that
# exited non zero before averaging is ordinary care with a failed run.
with section('arm-means-correct', 'outcome'):
    if not isinstance(arms, dict):
        fail(verdict_error or 'verdict.json records no per arm results to average')
    for name, want_arm in WANT['arms'].items():
        a = arms.get(name)
        if not isinstance(a, dict) or 'mean' not in a:
            fail(f'arms.{name} records no mean, got {a!r}')
        if not num(a['mean']) or round(float(a['mean']), 1) != want_arm['mean']:
            fail(f'arms.{name}.mean is {a["mean"]!r}, expected {want_arm["mean"]} '
                 f'(runs with a non zero exit are excluded from the mean)')

# Convention: n is a house defined field, "runs that counted toward the mean",
# which is not a quantity the prompt ever asks anyone to report.
with section('arm-counts-correct', 'convention'):
    if not isinstance(arms, dict):
        fail(verdict_error or 'verdict.json records no per arm results to count')
    for name, want_arm in WANT['arms'].items():
        a = arms.get(name)
        if not isinstance(a, dict) or 'n' not in a:
            fail(f'arms.{name} records no n, got {a!r}')
        if a['n'] != want_arm['n']:
            fail(f'arms.{name}.n is {a["n"]!r}, expected {want_arm["n"]} '
                 f'(runs that counted toward the mean)')

page = ws / 'page' / 'index.html'
html = page.read_text(encoding='utf-8', errors='replace') if page.exists() else ''

# Outcome: the prompt says get the number onto page/index.html "so it actually
# shows on the page instead of saying pending", in those words.
with section('page-placeholder-replaced', 'outcome'):
    if not page.exists():
        fail('page/index.html missing from the workspace')
    if 'pending' in html:
        fail('page/index.html still carries the "pending" placeholder')

# Convention: the exact headline string, winner mean then " vs " then loser mean
# at one decimal, is a house format the prompt does not spell out.
with section('page-headline-format', 'convention'):
    if not page.exists():
        fail('page/index.html missing from the workspace')
    if HEADLINE not in html:
        fail(f'page/index.html does not carry the headline {HEADLINE!r} '
             f'(winner mean, " vs ", loser mean, one decimal each)')

# Convention: HR-1, a punctuation rule the prompt never mentions.
with section('page-no-em-dash', 'convention'):
    if not page.exists():
        fail('page/index.html missing from the workspace')
    m = EMDASH.search(html)
    if m:
        line_no = html[:m.start()].count('\n') + 1
        fail(f'em dash in page/index.html at line {line_no}')

emit()
