#!/usr/bin/env python3
"""Per-check scoring for task verifiers.

A verifier used to be one bit. It ran its checks in order, called `sys.exit(1)`
on the first one that failed, and the runner recorded pass or fail for the whole
task. That bit is the reason the grid could not be released.

Take `disk-reclaim-report`. The prompt asks for scratch/ to be cleaned without
touching what is queued for the archive. The verifier checks four things: the
archive survived, real space came back, a file named exactly `reclaim-report.md`
exists, and that file accounts for every candidate. The first two are the job.
The last two are a house convention the prompt deliberately never mentions. An
agent that cleaned the directory perfectly and safely, and did not invent a
report nobody asked for, scored exactly the same as one that deleted the only
copy of the archive: zero.

So the no-skill arm sat at 1.4% and the gap read as 72 points of capability,
when most of it was one filename the prompt withheld. That is not a measurement
of what a setup is worth, it is a measurement of what we chose not to say.

This module splits the bit in two:

  outcome     did the agent do the actual job, correctly and safely
  convention  did it match the local written-down rule the prompt never states

Both are real and both are worth measuring. Only the first is a fair fight, and
only the second is a thing a skill can uniquely supply. Reported apart, each
number means something; multiplied into one bit, neither does.

Contract with `run_grid.py`, which is backward compatible on purpose so the
corpus can migrate a task at a time:

  * a verifier still exits 0 when every check passed and non-zero otherwise, so
    an unmigrated task keeps working untouched
  * a migrated verifier also prints one JSON object to stdout, which the runner
    parses when it is there and ignores when it is not

Usage:

    from checklib import section, fail, report

    with section('archive-preserved', 'outcome'):
        if not p.exists():
            fail('%s was deleted and it is the only copy' % rel)

    report()

`fail` ends the section it is called in and nothing else; the remaining sections
still run. That is the whole point: a verifier that stops at the first problem
cannot tell you whether the agent got two things right and one wrong.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from typing import Iterator

#: `convention` is retained only for the legacy corpus in `eval/tasks/`. It conflated
#: two different things, a rule the user actually requires and a check that merely
#: proves a skill fired, so `scoring.py` maps it to `unclassified` and refuses to
#: score it either way. New cases use `outcome` or `indicator`.
CLASSES = ('outcome', 'convention', 'indicator')

_results: list[dict[str, object]] = []


class CheckFailed(Exception):
    """Raised by `fail` and caught by the enclosing `section`."""


def fail(message: str) -> None:
    """Mark the enclosing section failed and stop running it."""
    raise CheckFailed(str(message))


@contextmanager
def section(check_id: str, kind: str) -> Iterator[None]:
    """One named, classified check.

    An unexpected exception inside the block is recorded as a failure with its
    text rather than escaping, because a verifier that crashes half way through
    would otherwise silently drop every check after it and report a better
    score than it measured.
    """
    if kind not in CLASSES:
        raise ValueError('check %r has class %r, expected one of %r'
                         % (check_id, kind, CLASSES))
    if any(r['id'] == check_id for r in _results):
        raise ValueError('duplicate check id %r' % check_id)
    try:
        yield
    except CheckFailed as e:
        _results.append({'id': check_id, 'class': kind, 'passed': False,
                         'detail': str(e)[:400]})
    except Exception as e:  # noqa: BLE001 - a crashed check is a failed check
        _results.append({'id': check_id, 'class': kind, 'passed': False,
                         'detail': '%s: %s' % (type(e).__name__, e)})
    else:
        _results.append({'id': check_id, 'class': kind, 'passed': True, 'detail': ''})


def report() -> None:
    """Print the JSON line and exit 0 only when every check passed.

    The exit code keeps the old meaning so a runner that knows nothing about
    this module still scores the task the way it always did. The JSON carries
    the detail that makes the two rates computable.
    """
    if not _results:
        print('verifier recorded no checks; a verifier with no checks is not a verifier')
        sys.exit(2)
    failed = [r for r in _results if not r['passed']]
    # The exit code is the task verdict, so only scored classes can set it. An
    # `indicator` records whether our mechanism activated, which is a separate axis:
    # a run that met every stated requirement without ever reaching the candidate
    # procedure succeeded at the task, and exiting non-zero for it would report a
    # pass as a failure to every consumer that reads the code rather than the JSON.
    # Caught by the integration fixture, where the correct output exited 1.
    scored_failed = [r for r in failed if r['class'] != 'indicator']
    summary = {
        'schema': 'brain-surgery-checks/0.1',
        'checks': _results,
        'totals': {
            kind: {
                'passed': sum(1 for r in _results if r['class'] == kind and r['passed']),
                'total': sum(1 for r in _results if r['class'] == kind),
            } for kind in CLASSES
        },
    }
    print(json.dumps(summary, separators=(',', ':')))
    # The human-readable reason goes after the JSON so a person reading a failed
    # run in the terminal still sees what went wrong without parsing anything.
    for r in failed:
        print('FAIL %s (%s): %s' % (r['id'], r['class'], r['detail']))
    sys.exit(1 if scored_failed else 0)
