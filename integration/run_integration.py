#!/usr/bin/env python3
"""Run the integration fixture across both adapters and score it through one contract.

Four runs: one case, two harnesses, two configurations, one attempt each. No retries,
no extra repetitions, no automatic anything. Repetition answers a question the first
runs raised; it does not happen by default.

This proves plumbing, not value. Both arms passing is a pass. A zero performance
difference is a pass. The failure modes that matter are an adapter that cannot run,
cannot place the candidate, returns no usable output, or produces a score that
disagrees with the other adapter on identical evidence.

Usage: run_integration.py [--harness claude,codex] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'integration' / 'case-csv-rollup'
sys.path.insert(0, str(ROOT / 'eval'))
from scoring import score_arm, score_run, score_task  # noqa: E402

PROTOCOL = 'brain-surgery-adapter/0.3'
ADAPTERS = {'claude': ROOT / 'adapters' / 'claude_adapter.py',
            'codex': ROOT / 'adapters' / 'codex_adapter.py'}
MODELS = {'claude': 'claude-sonnet-5', 'codex': 'gpt-5.2-codex'}


def build_request(task: dict, workspace: Path, harness: str, candidate: bool) -> dict:
    """The arm is never labelled. ADAPTER.md: the two configuration snapshots are the
    sole intended difference, and no current/candidate label is supplied."""
    configuration = {}
    if candidate:
        configuration['skill'] = {'name': task['skill'], 'source': str(CASE / 'skill')}
    return {
        'protocol': PROTOCOL,
        'model': MODELS[harness],
        'prompt': task['prompt'],
        'context': '',
        'configuration': json.dumps(configuration),
        'workspace': str(workspace),
        'invocation_mode': 'natural',
        'limits': {'seconds': 300, 'max_turns': 20},
        'instructions': 'Fresh session, restricted workspace; no external actions',
    }


def one_run(task: dict, harness: str, candidate: bool, dry: bool) -> dict:
    workspace = Path(tempfile.mkdtemp(prefix='bs-integration-'))
    for item in (CASE / 'workspace').iterdir():
        shutil.copy2(item, workspace / item.name)
    request = build_request(task, workspace, harness, candidate)

    arm = 'candidate' if candidate else 'baseline'
    if dry:
        return {'harness': harness, 'arm': arm, 'dry_run': True,
                'workspace': str(workspace), 'request': request}

    # Outside the workspace, because the verifier reads the workspace. Written
    # inside, the harness's own files became part of the evidence: the response
    # JSON happened to contain the digits the procedure indicator looks for, so
    # that check passed in the baseline arm, which has no procedure at all. A
    # harness contaminating its own measurement is the exact fault this fixture
    # exists to catch elsewhere.
    side = workspace.parent / (workspace.name + '-io')
    side.mkdir(exist_ok=True)
    rq = side / 'request.json'
    rs = side / 'response.json'
    rq.write_text(json.dumps(request, indent=1))
    subprocess.run([sys.executable, str(ADAPTERS[harness]),
                    '--request', str(rq), '--response', str(rs)],
                   capture_output=True, text=True, timeout=420)
    response = json.loads(rs.read_text()) if rs.exists() else {'status': 'infrastructure_error'}

    # Score from the checker, never from the adapter's opinion of its own run.
    checks = []
    if response.get('status') == 'ok':
        proc = subprocess.run([sys.executable, str(CASE / 'check.py'), str(workspace)],
                              capture_output=True, text=True, timeout=120)
        head = (proc.stdout or '').lstrip().split('\n', 1)[0]
        if head.startswith('{'):
            checks = json.loads(head).get('checks', [])

    scored = score_run(checks) if checks else {
        'scorable': False, 'task_passed': None,
        'unscorable_reason': 'adapter returned status %r' % response.get('status'),
        'checks': {}, 'invocation': None}
    return {'harness': harness, 'arm': arm, 'workspace': str(workspace),
            'adapter': {k: v for k, v in response.items() if k != 'stderr_tail'},
            'stderr_tail': response.get('stderr_tail'),
            'score': scored}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--harness', default='claude,codex')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--out', type=Path, default=ROOT / 'integration' / 'result.json')
    a = p.parse_args()

    task = json.loads((CASE / 'task.json').read_text())
    harnesses = [h.strip() for h in a.harness.split(',') if h.strip()]
    runs = [one_run(task, h, candidate, a.dry_run)
            for h in harnesses for candidate in (False, True)]

    if a.dry_run:
        print(json.dumps(runs, indent=1)[:2000])
        return 0

    summary = {}
    for h in harnesses:
        summary[h] = {}
        for arm in ('baseline', 'candidate'):
            hits = [r['score'] for r in runs if r['harness'] == h and r['arm'] == arm]
            summary[h][arm] = score_arm([score_task(hits)])

    result = {'case': task['id'], 'kind': task['kind'], 'runs': runs, 'summary': summary}
    a.out.write_text(json.dumps(result, indent=1))

    print(f'\n{"harness":9s} {"arm":10s} {"status":22s} {"passed":7s} loaded')
    print('-' * 64)
    for r in runs:
        ad = r.get('adapter') or {}
        inv = (ad.get('invocation') or {}).get('target_loaded')
        status = ad.get('status', '?')
        if not r['score'].get('scorable'):
            status = r['score'].get('unscorable_reason', status)[:22]
        print(f'{r["harness"]:9s} {r["arm"]:10s} {status:22s} '
              f'{str(r["score"].get("task_passed")):7s} {inv}')
    print(f'\nwrote {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
