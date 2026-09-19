#!/usr/bin/env python3
"""Turn a Brain Surgery inspection into scan findings.

Read-only. No evaluation, no execution, no configuration change. Every number
here is counted from the user's own transcripts and skill files; nothing is
modelled, projected, or inferred from a sample.

The scan answers one question: of the capability installed on this machine,
how much does the agent actually reach, and what is quietly broken?
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import Counter
from pathlib import Path
from typing import Any

from inspect_setup import bare_skill_name

SCHEMA = 'brain-surgery-scan/0.1'

# A finding is only emitted when the transcripts support it. Each carries the
# evidence that produced it so the report can show its work.
SEVERITY = {'load_failed': 3, 'shadowed': 2, 'inventory_gap': 2, 'duplicated': 1, 'dormant': 1}

#: How much weight a finding can carry, which is a different question from how
#: alarming it sounds. Ordering the report by severity alone put "163 of your skills
#: were never used" at the top, and dormancy is not a defect: most of those skills
#: are for work the user does not do, and installing something you never need is not
#: a fault. A fresh machine with five cleanly installed skills produced exactly one
#: finding, that one, which would have told a new user their setup was 80% broken
#: when nothing was wrong with it at all.
#:
#:   confirmed    reproducible by inspection right now
#:   suspected    historical evidence only; the condition may already be gone
#:   observation  true, and not necessarily anything to fix
CONFIDENCE = {
    'shadowed': 'confirmed',       # two DIFFERENT files on disk today, both readable
    'duplicated': 'observation',   # same bytes twice; nothing behaves differently
    'load_failed': 'suspected',    # an error in a past transcript, not re-tested
    'inventory_gap': 'suspected',  # may be host-bundled and have no path at all
    'dormant': 'observation',
    'no_evidence': 'observation',
}
BUCKET_ORDER = {'confirmed': 3, 'suspected': 2, 'observation': 1}


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not str(data.get('schema_version', '')).startswith('brain-surgery-inspection/'):
        raise SystemExit(f'Not an inspection file: {path}')
    return data


def usage(sessions: list[dict[str, Any]]) -> tuple[Counter, Counter, Counter]:
    """Attempts, confirmed loads, and explicitly failed loads, by skill name.

    Failures are only those the transcript flagged as errors. An attempt with no
    matched result is left out of both: a truncated trace is not a failure.

    Keyed on the bare skill name. A plugin skill appears in a transcript as
    `plugin:skill` and in its own SKILL.md as `skill`; counting the two separately
    splits one skill's usage across two keys and leaves the installed half at zero.
    """
    attempts: Counter = Counter()
    loads: Counter = Counter()
    failures: Counter = Counter()
    for session in sessions:
        for key, sink in (('skill_attempts', attempts),
                          ('confirmed_skill_loads', loads),
                          ('failed_skill_loads', failures)):
            for event in session.get(key, []):
                name = bare_skill_name(event.get('name'))
                if name:
                    sink[name] += 1
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


def distinct_files(paths: list[str]) -> list[str]:
    """Collapse paths that resolve to one file.

    `~/.agents/skills/x/SKILL.md` and `~/.claude/skills/x/SKILL.md` are usually the
    same file: one canonical copy, symlinked into each harness root, which is the
    layout the docs recommend. Reporting that as a name collision tells a user their
    correct setup is broken.
    """
    seen, out = set(), []
    for path in sorted(p for p in paths if p):
        try:
            real = os.path.realpath(path)
        except OSError:
            real = path
        if real in seen:
            continue
        seen.add(real)
        out.append(path)
    return out


def all_namespaced(paths: list[str]) -> bool:
    """True when every copy lives inside a distinct plugin.

    Plugin skills load under `plugin:skill`, so they do not compete for a trigger
    even when their bare names match. Only a name claimed twice within one plugin,
    or once in a plugin and once in a plain skill root, can actually shadow.
    """
    owners = set()
    for path in paths:
        parts = Path(path).parts
        if 'plugins' not in parts:
            return False
        index = len(parts) - 1 - parts[::-1].index('plugins')
        owners.add('/'.join(parts[:index + 2]))
    return len(owners) == len(paths)


def deduplicate(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse findings that share one root cause.

    `gmail-operations` appeared twice on a real scan: once as a skill whose every
    load attempt errored, and once as a skill absent from the inventory. Those are
    one fault, a missing symlink, counted twice, and a defect count built by adding
    findings together overstates the work by however many symptoms each cause
    happens to produce.

    Keeps the finding with the highest confidence and records what merged into it,
    so nothing is hidden, only counted once.
    """
    by_skill: dict[str, list[dict[str, Any]]] = {}
    out: list[dict[str, Any]] = []
    for f in findings:
        name = f.get('skill')
        if name:
            by_skill.setdefault(name, []).append(f)
        else:
            out.append(f)
    for name, group in by_skill.items():
        group.sort(key=lambda f: -BUCKET_ORDER.get(f.get('confidence', 'observation'), 0))
        primary = dict(group[0])
        if len(group) > 1:
            primary['also_reported_as'] = [g['code'] for g in group[1:]]
            primary['detail'] += (
                ' The same underlying fault also shows up as %s, counted once here.'
                % ' and '.join(g['code'].replace('_', ' ') for g in group[1:]))
        out.append(primary)
    return out


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
    #
    #    Re-verified, not just reported. A transcript error is evidence about the
    #    moment it happened, and setups get fixed: `gmail-operations` and
    #    `agentwallet-credential-ops` both failed every attempt in the window and
    #    both resolve on disk today, because the missing symlinks were added after
    #    those sessions ran. Reporting them as current faults sends the user to fix
    #    something that is already fixed, which is the fastest way to teach them the
    #    scan is not worth reading.
    resolvable = {bare_skill_name(a) for sk in skills for a in (sk.get('aliases') or [])
                  if a} | installed
    resolved = []
    for name, count in sorted(failures.items(), key=lambda kv: -kv[1]):
        if bare_skill_name(name) in resolvable:
            resolved.append(name)
            continue
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
    #
    #    Two ways this over-reports, both found by running it against real trees:
    #
    #    A plugin skill loads as `plugin:skill`, so the same bare name in three
    #    different plugins is three namespaced skills, not a collision. On a real
    #    marketplace cache, `access` and `configure` each appeared three times,
    #    across imessage, telegram and discord. Neither shadows anything.
    #
    #    A canonical skill symlinked into several harness roots is one file seen
    #    from several paths. That is the recommended layout, not a fault.
    by_name: dict[str, list[dict[str, Any]]] = {}
    for s in skills:
        by_name.setdefault(s['name'], []).append(s)
    for name, entries in sorted(by_name.items()):
        paths = distinct_files([e.get('path', '') for e in entries])
        if len(paths) < 2 or all_namespaced(paths):
            continue
        # Identical copies are not a collision in any sense the user can feel.
        # Whichever one the host loads, the skill is the same. Every collision on
        # the first real machine scanned was this: one canonical skill copied,
        # rather than symlinked, into a second harness root. Reporting that as
        # something to fix invents work and teaches the reader to ignore the scan.
        # Every copy must carry a digest. Dropping the ones that do not would leave
        # a single value behind and read as "identical", downgrading a real
        # collision on the strength of a field nobody filled in.
        digests = [e.get('skill_md_sha256') for e in entries]
        identical = (len(entries) == len(paths)
                     and all(digests) and len(set(digests)) == 1)
        findings.append({
            'code': 'duplicated' if identical else 'shadowed',
            'skill': name,
            'title': (f'{name} is stored twice, identically'
                      if identical else
                      f'{name} is declared in {len(paths)} places, and they differ'),
            'detail': ('Both copies are byte-identical, so whichever one loads you get the '
                       'same skill and nothing is broken today. Worth knowing only because '
                       'editing one will silently leave the other behind.'
                       if identical else
                       'Two different files claim this name. One wins and the other never '
                       'loads, and which one wins is not something you chose. Compare them '
                       'and keep one.'),
            'evidence': {'paths': sorted(paths),
                         'identical': identical,
                         'digests': sorted({d for d in digests if d})},
        })

    # 3. A skill the transcripts show loading that the inventory never saw. Means
    #    a skill root is missing, so the rest of the scan is under-counting.
    for name in data.get('inventory_gap', []):
        findings.append({
            'code': 'inventory_gap',
            'skill': name,
            'title': f'{name} loaded but was not found on disk',
            'detail': 'This skill ran but no scanned root holds its SKILL.md. Either it ships '
                      'inside the host agent itself and has no path to find, or it has been '
                      'moved or removed since it last ran. Only the second is something to '
                      'fix; either way the counts below are a floor, not a ceiling.',
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

    for f in findings:
        f['confidence'] = CONFIDENCE.get(f['code'], 'observation')

    findings = deduplicate(findings)
    # Bucket first, severity second. A confirmed collision outranks a suspected load
    # failure even though the failure sounds worse, because the reader can act on one
    # of them today and can only guess about the other.
    findings.sort(key=lambda f: (-BUCKET_ORDER.get(f['confidence'], 0),
                                 -SEVERITY.get(f['code'], 0)))

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
        # Named so the report can say what stopped failing, rather than silently
        # dropping a finding the user may remember seeing.
        'resolved_since': sorted(resolved),
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
