#!/usr/bin/env python3
"""Turn a Brain Surgery inspection into scan findings.

Read-only. No evaluation, no execution, no configuration change. Every number
here is counted from the user's own transcripts and skill files; nothing is
modelled, projected, or inferred from a sample.

The scan answers one question: of the capability installed on this machine,
how much does the agent actually reach, and what is quietly broken?
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = 'brain-surgery-scan/0.1'

# A finding is only emitted when the transcripts support it. Each carries the
# evidence that produced it so the report can show its work.
SEVERITY = {'load_failed': 3, 'shadowed': 2, 'inventory_gap': 2, 'dormant': 1}


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not str(data.get('schema_version', '')).startswith('brain-surgery-inspection/'):
        raise SystemExit(f'Not an inspection file: {path}')
    return data


def usage(sessions: list[dict[str, Any]]) -> tuple[Counter, Counter, Counter]:
    """Attempts, confirmed loads, and explicitly failed loads, by skill name.

    Failures are only those the transcript flagged as errors. An attempt with no
    matched result is left out of both: a truncated trace is not a failure.
    """
    attempts: Counter = Counter()
    loads: Counter = Counter()
    failures: Counter = Counter()
    for session in sessions:
        for key, sink in (('skill_attempts', attempts),
                          ('confirmed_skill_loads', loads),
                          ('failed_skill_loads', failures)):
            for event in session.get(key, []):
                if event.get('name'):
                    sink[event['name']] += 1
    return attempts, loads, failures


# Warning text from the inspector, mapped to a category the public report can
# name without leaking the path or skill name the warning carries. Anything
# unrecognised is reported as 'other' with no text, so a new warning cannot leak.
WARNING_KINDS = (
    ('Total transcript read budget exhausted', 'read_budget_exhausted'),
    ('Row cap reached', 'row_cap_reached'),
    ('oversized row', 'oversized_rows_skipped'),
    ('Skill root not found', 'skill_root_missing'),
    ('Loaded but not inventoried', 'inventory_gap'),
    ('No transcripts', 'no_transcripts'),
)
# Those that mean the scan did not read everything it was pointed at, so the
# dormant count is a ceiling and the reached count a floor.
TRUNCATING = {'read_budget_exhausted', 'row_cap_reached', 'oversized_rows_skipped'}


def scan_limits(data: dict[str, Any]) -> dict[str, Any]:
    """Whether the scan read everything it was pointed at, and if not, why.

    A truncated scan that does not say it is truncated is the same failure as a
    fabricated number: the reader cannot tell a measurement from a partial one.
    """
    warnings = [w for w in data.get('warnings', []) if isinstance(w, str)]
    kinds: list[str] = []
    for warning in warnings:
        kind = next((k for needle, k in WARNING_KINDS if needle in warning), 'other')
        if kind not in kinds:
            kinds.append(kind)
    truncated = bool(TRUNCATING & set(kinds))
    return {
        'complete': not truncated,
        'reasons': kinds,
        'effect': ('Some transcripts were not read in full, so the dormant count is an upper '
                   'bound and the reached count a lower bound.') if truncated else None,
        # Raw text carries paths and skill names. Local report only.
        'warnings': warnings,
    }


def coverage(data: dict[str, Any]) -> dict[str, Any]:
    sessions = data.get('sessions', [])
    kinds = Counter(s.get('invocation_coverage') for s in sessions)
    return {
        'sessions_analyzed': len(sessions),
        'turns_analyzed': sum(len(s.get('turns', [])) for s in sessions),
        'window_days': data.get('limits', {}).get('days'),
        'session_cap': data.get('limits', {}).get('max_sessions'),
        'invocation_coverage': dict(kinds),
        # The inspector cannot prove a negative across an unread transcript.
        'absence_is_not_zero': True,
        'caveat': ('Counts cover the sessions read in this scan, not your whole history. '
                   'A skill with no recorded load was not reached in this window; '
                   'that is not proof it was never useful.'),
    }


def analyze(data: dict[str, Any]) -> dict[str, Any]:
    skills = [s for s in data.get('skills', []) if s.get('name')]
    sessions = data.get('sessions', [])
    attempts, loads, failures = usage(sessions)

    installed = {s['name'] for s in skills}
    loaded = {n for n, c in loads.items() if c > 0}
    # Some skills load from outside the scanned roots, so 'loaded' is not a subset
    # of 'installed'. Keep the two apart: reached + dormant must equal installed,
    # or a report that subtracts them silently invents a category.
    reached = installed & loaded
    outside = sorted(loaded - installed)
    dormant = sorted(installed - loaded)

    findings: list[dict[str, Any]] = []

    # 1. Skills the agent tried to load and could not. These are breakages the
    #    user is paying for and cannot see.
    for name, count in sorted(failures.items(), key=lambda kv: -kv[1]):
        findings.append({
            'code': 'load_failed',
            'skill': name,
            'title': f'{name} failed when your agent tried to use it',
            'detail': f'Your agent reached for this skill {count} time{"" if count == 1 else "s"} in the scanned window '
                      'and the load returned an error, so the work continued without it.',
            'evidence': {'attempts': attempts.get(name, 0), 'confirmed_loads': loads.get(name, 0),
                         'failed': count},
        })

    # 2. Two skill directories declaring the same name. One silently shadows the
    #    other and which one wins is not something the user chose.
    by_name: dict[str, list[str]] = {}
    for s in skills:
        by_name.setdefault(s['name'], []).append(s.get('path', ''))
    for name, paths in sorted(by_name.items()):
        if len(paths) > 1:
            findings.append({
                'code': 'shadowed',
                'skill': name,
                'title': f'{name} is declared in {len(paths)} places',
                'detail': 'Two skill files claim the same name. One of them wins and the other '
                          'never loads. Which one wins is not something you chose.',
                'evidence': {'paths': sorted(paths)},
            })

    # 3. A skill the transcripts show loading that the inventory never saw. Means
    #    a skill root is missing, so the rest of the scan is under-counting.
    for name in data.get('inventory_gap', []):
        findings.append({
            'code': 'inventory_gap',
            'skill': name,
            'title': f'{name} loaded but was not found on disk',
            'detail': 'This skill ran but lives outside the scanned roots, so the counts below '
                      'are a floor, not a ceiling.',
            'evidence': {'confirmed_loads': loads.get(name, 0)},
        })

    # 4. The headline. Installed capability the agent never reached.
    #    Only sayable when transcripts were actually read. With no sessions every
    #    skill trivially looks dormant, which would turn an empty scan into the
    #    most alarming possible finding, invented out of nothing.
    measurable = bool(installed) and len(sessions) > 0
    if measurable:
        findings.append({
            'code': 'dormant',
            'skill': None,
            'title': f'{len(dormant)} of {len(installed)} installed skills were never used',
            'detail': 'These are installed and available. In the scanned window your agent did '
                      'not load them once.',
            'evidence': {'installed': len(installed), 'reached': len(reached),
                         'dormant': len(dormant), 'names': dormant},
        })
    elif installed:
        findings.append({
            'code': 'no_evidence',
            'skill': None,
            'title': f'{len(installed)} skills found, but no sessions could be read',
            'detail': 'Nothing here is a measurement. This is not evidence that your setup is '
                      'healthy, and it is not evidence that anything is wrong.',
            'evidence': {'installed': len(installed), 'sessions_analyzed': len(sessions)},
        })

    findings.sort(key=lambda f: -SEVERITY.get(f['code'], 0))

    return {
        'schema_version': SCHEMA,
        'created_at': data.get('created_at'),
        'project': data.get('project'),
        'host': data.get('host'),
        'evaluation_performed': False,
        'change_status': 'not_applied',
        'totals': {
            # False means no transcript was read, so 'dormant' below is an artefact of
            # having measured nothing. Renderers must not show a dormancy headline here.
            'measured': measurable,
            'installed': len(installed),
            'reached': len(reached),
            'dormant': len(dormant),
            # Loaded but not in the inventory. Not part of installed, so it is
            # reported beside the split rather than folded into either side.
            'loaded_outside_inventory': len(outside),
            'dormant_percent': round(100 * len(dormant) / len(installed)) if measurable else None,
            'load_attempts': sum(attempts.values()),
            'confirmed_loads': sum(loads.values()),
            'failed_loads': sum(failures.values()),
        },
        'most_used': [{'skill': n, 'loads': c} for n, c in loads.most_common(10)],
        'findings': findings,
        'coverage': coverage(data),
        'scan_limits': scan_limits(data),
        'privacy': 'Counts and skill names only. No prompts, task text, or file contents.',
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True, help='inspection JSON from inspect_setup.py')
    p.add_argument('--out', type=Path, help='write scan result JSON here')
    args = p.parse_args()

    result = analyze(load(args.input))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    t = result['totals']
    print(json.dumps({'installed': t['installed'], 'reached': t['reached'],
                      'dormant': t['dormant'], 'failed_loads': t['failed_loads'],
                      'findings': len(result['findings']),
                      'out': str(args.out) if args.out else None}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
