#!/usr/bin/env python3
"""Claude Code adapter for `brain-surgery-adapter/0.3`.

Runs one arm of one case and writes evidence back. It does not score: scoring is
`eval/scoring.py`, shared by every adapter, because a customer must not get a
different definition of the number depending on which harness they use.

## The comparison this implements

Current setup versus current setup plus one candidate change. **Not** setup versus
no setup. The baseline arm is the user's real configuration, untouched. The
candidate arm is that same configuration with one skill added, project-local, inside
the disposable workspace.

That matters because "does your setup help at all" and "does our recommendation help"
are different questions, and only the second is the one a recommendation has to
answer. It is also why this does not use `claude plugin eval` for the personal
number: that runner deliberately omits personal settings, memory, other plugins and
project instructions, which is useful isolation and the wrong baseline for us.

## Why nothing global is touched

The candidate skill is written into `<workspace>/.claude/skills/<name>/`, which is a
project-local search path. The user's `~/.claude` is never renamed, moved, copied or
modified. Removing the workspace removes the entire difference between the arms.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROTOCOL = 'brain-surgery-adapter/0.3'


def place_candidate(workspace: Path, configuration: dict) -> str | None:
    """Install the candidate skill project-locally, or nothing for the baseline arm.

    The arm is never named in the request, per ADAPTER.md: the two configuration
    snapshots are the only intended difference, and a backend told which side it is
    on can behave differently for reasons that have nothing to do with the setup.
    """
    skill = configuration.get('skill')
    if not skill:
        return None
    name, source = skill['name'], Path(skill['source'])
    dest = workspace / '.claude' / 'skills' / name
    dest.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, dest / item.name)
    return name


def detect_load(stream: list[dict], skill: str | None) -> bool | None:
    """Whether the candidate was actually opened.

    `None`, not `False`, when there is no candidate or no usable trace. ADAPTER.md is
    explicit that a mention in reasoning or a skill listing is not a confirmed load,
    and that unknown must not read as zero.
    """
    if not skill:
        return None
    saw_trace = False
    for event in stream:
        for block in (event.get('message') or {}).get('content') or []:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'tool_use':
                saw_trace = True
                if block.get('name') == 'Skill':
                    value = json.dumps(block.get('input') or {})
                    if re.search(r'\b%s\b' % re.escape(skill), value):
                        return True
    return False if saw_trace else None


def run(request: dict) -> dict:
    workspace = Path(request['workspace']).resolve()
    skill = place_candidate(workspace, json.loads(request['configuration']))
    limits = request.get('limits') or {}

    cmd = [
        'claude', '-p', request['prompt'],
        '--output-format', 'stream-json', '--verbose',
        '--model', request['model'],
        '--permission-mode', 'acceptEdits',
        '--add-dir', str(workspace),
        # Both arms load the user's real settings. The only difference is the
        # project-local skill the candidate arm carries in its workspace.
        '--setting-sources', 'user,project',
    ]
    if limits.get('max_turns'):
        cmd += ['--max-turns', str(limits['max_turns'])]

    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True,
                              timeout=limits.get('seconds', 300))
    except subprocess.TimeoutExpired:
        return {'protocol': PROTOCOL, 'model': request['model'],
                'status': 'infrastructure_error', 'error': 'timed out',
                'usage': {'total_tokens': None},
                'invocation': {'complete': False, 'target_loaded': None}}

    stream = []
    for line in (proc.stdout or '').splitlines():
        line = line.strip()
        if line.startswith('{'):
            try:
                stream.append(json.loads(line))
            except ValueError:
                pass

    usage = {}
    for event in stream:
        if event.get('type') == 'result':
            usage = event.get('usage') or {}
    total = sum(v for k, v in usage.items()
                if k.endswith('tokens') and isinstance(v, (int, float)))

    # A crash or a broken answer is a task failure, not an excluded sample. Only a
    # run that never reached the model is infrastructure.
    status = 'ok' if stream else 'infrastructure_error'
    return {
        'protocol': PROTOCOL,
        'model': request['model'],
        'status': status,
        'usage': {'total_tokens': int(total) or None, 'raw': usage},
        'invocation': {'complete': bool(stream),
                       'target_loaded': detect_load(stream, skill)},
        'seconds': round(time.time() - started, 1),
        'harness': 'claude',
        'returncode': proc.returncode,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path, required=True)
    p.add_argument('--response', type=Path, required=True)
    a = p.parse_args()
    request = json.loads(a.request.read_text())
    if request.get('protocol') != PROTOCOL:
        a.response.write_text(json.dumps({
            'protocol': PROTOCOL, 'status': 'infrastructure_error',
            'error': 'unsupported protocol %r' % request.get('protocol')}))
        return 0
    a.response.write_text(json.dumps(run(request), indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
