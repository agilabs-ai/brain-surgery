#!/usr/bin/env python3
"""Codex adapter for `brain-surgery-adapter/0.3`.

Same contract and same comparison as the Claude adapter: current setup versus
current setup plus one candidate change, with scoring left to `eval/scoring.py` so
the number means the same thing on both harnesses.

## The open question this adapter exists to settle

Codex has no native evaluator. Inspection established that it reads skills from
repository, user and bundled sources, that `$CODEX_HOME` is honoured for config
layering, and that every `[[skills.config]]` entry in this machine's config is
`enabled = false`. **None of that proves a project-local skill is actually reachable
at runtime**, and absence from a listing is not proof of inaccessibility either.

So this adapter reports what it observes rather than asserting isolation worked. If
the candidate skill cannot be placed where Codex will reach it, the right result is a
failed compatibility check, not a quietly approximated comparison.

## Why nothing global is touched

The candidate skill is written into `<workspace>/.agents/skills/<name>/`, a
repository-level source. The user's `~/.codex` is never renamed, moved or modified,
and no environment redirection is used, so auth and config stay exactly where they
are. Removing the workspace removes the entire difference between the arms.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROTOCOL = 'brain-surgery-adapter/0.3'
SKILL_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')


def unsupported_request(request: dict) -> str | None:
    """Fail before launch when the Codex CLI cannot enforce a requested limit."""
    limit = (request.get('limits') or {}).get('max_total_tokens')
    if limit is not None:
        return 'Codex CLI cannot enforce limits.max_total_tokens; no model call was made'
    return None


def prompt_with_contract(request: dict) -> str:
    return (f"<run_instructions>\n{request.get('instructions', '')}\n</run_instructions>\n\n"
            f"<permitted_context>\n{request.get('context', '')}\n</permitted_context>\n\n"
            f"<task>\n{request['prompt']}\n</task>")


def place_candidate(workspace: Path, configuration: dict) -> str | None:
    skill = configuration.get('skill')
    if not skill:
        return None
    name, source = skill['name'], Path(skill['source']).resolve()
    if not isinstance(name, str) or not SKILL_NAME.fullmatch(name):
        raise ValueError('candidate skill name must be one safe path component')
    if not source.is_dir() or any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError('candidate skill source must be a directory without symlinks')
    dest = workspace / '.agents' / 'skills' / name
    if dest.exists():
        raise ValueError('candidate skill destination already exists')
    dest.mkdir(parents=True)
    for item in source.iterdir():
        if item.is_file():
            shutil.copy2(item, dest / item.name)
        elif item.is_dir():
            shutil.copytree(item, dest / item.name)
    return name


def detect_load(text: str, skill: str | None) -> bool | None:
    """Codex has no Skill tool event to key on, so this is weaker evidence than the
    Claude side and is reported as such.

    A bare name match in output would count the agent merely mentioning the file, so
    it requires the name next to a read or load verb. When nothing in the transcript
    could have carried the signal either way, the answer is `None`, never `False`."""
    if not skill:
        return None
    if not text.strip():
        return None
    pattern = r'(read|load|open|cat|apply|follow)[^\n]{0,80}%s' % re.escape(skill)
    if re.search(pattern, text, re.I):
        return True
    return False


#: A run that never reached the model is infrastructure, never a task failure.
#: The first integration run hit the Codex usage limit, exited 1 after 27 seconds
#: having produced nothing, and was recorded as a *failed task* because stdout was
#: non-empty. That scores an outage as evidence about the setup, which is the one
#: thing ADAPTER.md is most explicit about. Matched against combined stdout+stderr
#: because the CLI writes these to stderr.
INFRASTRUCTURE = (
    r"you've hit your usage limit",
    r'\brate.?limit',
    r'\bnot logged in\b|\bplease (run )?codex login\b|\bauthentication (failed|required)\b',
    r'\b(401|403|429|5\d\d)\b.{0,40}\b(unauthorized|forbidden|too many requests|server error)\b',
    r'\bnetwork (error|unreachable)\b|\bconnection (refused|reset)\b',
)


def classify_status(returncode: int, out: str) -> str:
    """`ok`, `task_failed` or `infrastructure_error`.

    `ok` means the agent ran and produced work for the verifier to judge; whether
    that work is correct is the verifier's call, not this one. A nonzero exit with
    real output is still `ok`, because an agent can finish badly and that is a task
    outcome. Only an outage, an auth failure or an empty run is infrastructure.
    """
    for pattern in INFRASTRUCTURE:
        if re.search(pattern, out, re.I):
            return 'infrastructure_error'
    if not out.strip():
        return 'infrastructure_error'
    return 'ok'


def run(request: dict) -> dict:
    unsupported = unsupported_request(request)
    if unsupported:
        return {'protocol': PROTOCOL, 'model': request.get('model'),
                'status': 'infrastructure_error', 'error': unsupported,
                'usage': {'total_tokens': 0},
                'invocation': {'complete': False, 'target_loaded': None},
                'harness': 'codex'}
    workspace = Path(request['workspace']).resolve()
    skill = place_candidate(workspace, json.loads(request['configuration']))
    limits = request.get('limits') or {}

    cmd = ['codex', 'exec',
           '--cd', str(workspace),
           '--sandbox', 'workspace-write',
           '--model', request['model'],
           '--ephemeral',
           '--skip-git-repo-check',
           prompt_with_contract(request)]

    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True,
                              timeout=limits.get('seconds', 300))
    except subprocess.TimeoutExpired:
        return {'protocol': PROTOCOL, 'model': request['model'],
                'status': 'infrastructure_error', 'error': 'timed out',
                'usage': {'total_tokens': None},
                'invocation': {'complete': False, 'target_loaded': None},
                'harness': 'codex'}

    out = (proc.stdout or '') + (proc.stderr or '')
    # Codex prints a usage summary rather than a structured result event. Parsed
    # where present, left as None where not, because ADAPTER.md requires
    # provider-reported usage and forbids guessing it from string lengths.
    tokens = None
    m = re.search(r'tokens used[^0-9]{0,20}([\d,]+)', out, re.I)
    if m:
        tokens = int(m.group(1).replace(',', ''))

    status = classify_status(proc.returncode, out)
    return {
        'protocol': PROTOCOL,
        'model': request['model'],
        'status': status,
        'usage': {'total_tokens': tokens},
        'invocation': {'complete': bool(out.strip()),
                       'target_loaded': detect_load(out, skill)},
        'seconds': round(time.time() - started, 1),
        'harness': 'codex',
        'returncode': proc.returncode,
        # Kept so a failed compatibility check can be diagnosed rather than guessed.
        'stderr_tail': (proc.stderr or '')[-600:],
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
