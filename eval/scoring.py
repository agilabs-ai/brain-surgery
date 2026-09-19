#!/usr/bin/env python3
"""The scoring contract. One definition of the number, whoever ran the task.

Execution is per harness. Scoring is not. A customer must not receive a different
definition of "83%" depending on whether they ran Claude or Codex, so every adapter
returns evidence and this module turns evidence into the score. Two programs may
implement the contract; they may not implement two contracts.

That is the whole reason this is a separate module from any runner.

## The headline is tasks, not checks

`task_passed` is true when every predeclared outcome criterion for that task was met.
It is not the fraction of checks that passed.

The difference is not academic. An output that satisfies nine formatting checks and
gets the required calculation wrong scores 90% on checks and is a failed task. Both
numbers are computable; only one of them answers "did this work". The check fractions
are reported underneath as explanation, never as the headline.

## Three classes, because two of them were previously one

- `outcome`     a requirement the user actually has. Counts toward `task_passed`.
                A file format the user genuinely requires is an outcome, not a
                technicality, so "convention" is not automatically excluded.
- `indicator`   evidence that our mechanism activated, such as a check that only
                passes when a particular skill loaded. Reported beside the score and
                never inside it, because a mechanism firing is not a task succeeding.
- `unclassified` the legacy `convention` label. It conflated the two above: some of
                those checks test something the user requires, others only prove the
                skill fired. It is not silently scored either way. A task carrying
                unclassified checks reports `scorable: false` with the count, so the
                ambiguity surfaces instead of resolving itself into a number.

Note the platform's own rule, which this mirrors: under a two-arm ablation,
`claude plugin eval` excludes `with-only` graders from the score and treats them as a
plugin-fired indicator, except when *every* grader qualifies, in which case they are
scored anyway. A task whose only checks are indicators measures nothing about
outcomes, so here it is `scorable: false` rather than silently scored.
"""
from __future__ import annotations

from typing import Any, Iterable

CONTRACT = 'brain-surgery-scoring/0.1'

OUTCOME = 'outcome'
INDICATOR = 'indicator'
UNCLASSIFIED = 'unclassified'

#: Legacy labels written by `checklib` before the three-class split. `convention`
#: is deliberately not mapped to either scoring class: see the module docstring.
LEGACY = {'outcome': OUTCOME, 'convention': UNCLASSIFIED}


def classify(check: dict[str, Any]) -> str:
    kind = str(check.get('class', '')).strip()
    return LEGACY.get(kind, kind if kind in (OUTCOME, INDICATOR) else UNCLASSIFIED)


def score_run(checks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One arm of one task, scored from its check results.

    Takes check results rather than a workspace on purpose. An adapter that ran the
    task natively can hand back the verdicts it already produced, and we can re-score
    saved outputs later without re-running anything. Identical evidence in, identical
    score out, which is the property the cross-adapter test pins.
    """
    rows = [dict(c, _class=classify(c)) for c in checks]
    buckets = {k: [r for r in rows if r['_class'] == k]
               for k in (OUTCOME, INDICATOR, UNCLASSIFIED)}
    outcome = buckets[OUTCOME]

    # A task with no outcome criterion has nothing to succeed at. Reporting it as a
    # pass would count a run that was never tested, and reporting it as a failure
    # would blame the run for a check nobody wrote.
    scorable = bool(outcome) and not buckets[UNCLASSIFIED]
    return {
        'contract': CONTRACT,
        'scorable': scorable,
        'task_passed': all(bool(r.get('passed')) for r in outcome) if scorable else None,
        'unscorable_reason': (
            None if scorable else
            'no outcome criteria declared' if not outcome else
            f'{len(buckets[UNCLASSIFIED])} checks still carry the legacy `convention` '
            'label and must be reclassified as outcome or indicator'),
        # Explanation, never the headline.
        'checks': {k: {'passed': sum(1 for r in v if r.get('passed')), 'total': len(v)}
                   for k, v in buckets.items()},
        # Separate axis. A skill firing is not a task succeeding, and a task
        # succeeding without it is not a skill failing.
        'invocation': {'fired': any(bool(r.get('passed')) for r in buckets[INDICATOR]),
                       'checked': len(buckets[INDICATOR])} if buckets[INDICATOR] else None,
    }


def score_task(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One task, one arm, across its repeated runs.

    The task's score is the fraction of scorable runs that passed. Unscorable runs
    are excluded and counted, never averaged in as zero.
    """
    scored = [r for r in runs if r.get('scorable')]
    return {
        'contract': CONTRACT,
        'runs': len(list(runs)) if not isinstance(runs, list) else len(runs),
        'scored_runs': len(scored),
        'passed_runs': sum(1 for r in scored if r.get('task_passed')),
        'rate': (sum(1 for r in scored if r.get('task_passed')) / len(scored)
                 if scored else None),
    }


def score_arm(tasks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One arm, across tasks. Task-macro, so a task with many runs cannot outvote one
    with few. Tasks with no scorable run are excluded and counted."""
    rates = [t['rate'] for t in tasks if t.get('rate') is not None]
    return {
        'contract': CONTRACT,
        'tasks': len(list(tasks)) if not isinstance(tasks, list) else len(tasks),
        'scored_tasks': len(rates),
        # "Percentage of tested tasks meeting their predeclared success criteria."
        'pass_rate': round(100.0 * sum(rates) / len(rates), 1) if rates else None,
    }
