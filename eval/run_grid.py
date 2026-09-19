#!/usr/bin/env python3
"""Run the model x setup grid and record one JSON record per (arm, task, trial).

Four arms, following SkillsBench's matched-condition design:

    A  base model    + no skill      baseline
    B  base model    + skill         setup lift  (B - A)
    C  stronger model + no skill     model lift  (C - A)
    D  stronger model + skill        do they stack (D - C, D - B)

Every arm sees the same prompt, the same seeded workspace and the same
deterministic check. The only things that move are the model and whether the
candidate skill is on disk. Each run gets a fresh workspace so nothing leaks
between trials, and the run order is shuffled so time-of-day drift spreads
evenly across arms instead of landing on one of them.

Isolation is the whole ballgame here. Each run gets its own CLAUDE_CONFIG_DIR
holding nothing but a copy of the OAuth credentials, so the host's installed
skills, settings, memory and session history are all invisible;
`--setting-sources ""` drops the user and project settings layers; and
`--plugin-dir` then adds back exactly the one skill the arm is supposed to
have. Without all three the host machine's own 80 installed skills leak into
the "no skill" arm and the comparison is meaningless.

Note the deliberate absence of `--bare`. It would be the tidier switch, but it
never reads OAuth, which would force this onto a metered API key. Running on
the subscription keeps the grid free, so the isolation is assembled by hand
instead.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ARMS = {
    'A': {'model_role': 'base', 'skill': False, 'label': 'base model, no skill'},
    'B': {'model_role': 'base', 'skill': True, 'label': 'base model, with skill'},
    'C': {'model_role': 'strong', 'skill': False, 'label': 'stronger model, no skill'},
    'D': {'model_role': 'strong', 'skill': True, 'label': 'stronger model, with skill'},
}


#: Resolved once at startup by `resolve_claude_bin`, never left to PATH.
CLAUDE_BIN = 'claude'

#: Hosts put wrappers ahead of the real binary on PATH. AX41's adds `--chrome`
#: to every invocation and rewrites the user's global config on each launch.
#: Either would wreck this measurement: a browser per run exhausts memory at any
#: useful worker count, and a wrapper that edits settings under 8 concurrent
#: workers is both a race and a breach of the isolation the arms depend on.
WRAPPER_DIRS = ('/usr/local/sbin',)


def resolve_claude_bin(explicit: str | None) -> str:
    """Find the real CLI, stepping over any wrapper shadowing it on PATH."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise SystemExit(f'--claude-bin {p} does not exist')
        return str(p)

    found = [Path(p) for p in shutil.which_all('claude')] if hasattr(shutil, 'which_all') else []
    if not found:
        # No which_all in the stdlib; walk PATH ourselves so every candidate is
        # visible rather than just the first.
        found = []
        for d in os.environ.get('PATH', '').split(os.pathsep):
            c = Path(d) / 'claude'
            if c.exists() and os.access(c, os.X_OK):
                found.append(c)
    if not found:
        raise SystemExit('no `claude` on PATH; pass --claude-bin')

    real = [c for c in found if str(c.parent) not in WRAPPER_DIRS and not is_wrapper(c)]
    chosen = real[0] if real else found[0]
    if chosen != found[0]:
        print(f'note: skipping wrapper {found[0]}, using {chosen}', flush=True)
    return str(chosen)


def is_wrapper(path: Path) -> bool:
    """A shell script that execs another claude is a wrapper, not the CLI."""
    try:
        with open(path, 'rb') as f:
            head = f.read(2048)
    except OSError:
        return False
    if not head.startswith(b'#!'):
        return False
    return b'claude' in head and (b'exec' in head or b'--chrome' in head)


def load_tasks(task_dir: Path, only=None):
    tasks = []
    for d in sorted(task_dir.iterdir()):
        if not d.is_dir() or not (d / 'task.json').exists():
            continue
        t = json.loads((d / 'task.json').read_text())
        t['dir'] = d
        if only and t['id'] not in only:
            continue
        # A smoke task exists to prove the harness runs end to end, and is built
        # to be passable by every arm. Scoring it would dilute the macro rate
        # with a cell that carries no signal, so it only runs when asked for.
        if t.get('smoke') and not (only and t['id'] in only):
            continue
        if not (d / 'check.py').exists():
            raise SystemExit(f'task {t["id"]} has no check.py; a task without a verifier is not a task')
        tasks.append(t)
    return tasks


def seed_workspace(task, ws: Path):
    """Materialise the task's starting files. Same bytes for every arm."""
    ws.mkdir(parents=True, exist_ok=True)
    src = task['dir'] / 'workspace'
    if src.exists():
        shutil.copytree(src, ws, dirs_exist_ok=True)
    for name, body in (task.get('seed') or {}).items():
        (ws / name).parent.mkdir(parents=True, exist_ok=True)
        (ws / name).write_text(body)


def build_plugin_dir(task, dest: Path):
    """Stage the candidate skill as a one-skill plugin.

    Claude Code discovers a plugin by its manifest, so the skill has to sit
    under `skills/<name>/SKILL.md` next to a `.claude-plugin/plugin.json`.
    """
    skill_src = ROOT / 'skills' / task['skill']
    if not skill_src.exists():
        raise SystemExit(f'task {task["id"]} names skill {task["skill"]}, which is not in eval/skills/')
    (dest / '.claude-plugin').mkdir(parents=True, exist_ok=True)
    (dest / '.claude-plugin' / 'plugin.json').write_text(json.dumps({
        'name': f'bs-{task["skill"]}',
        'version': '0.0.0',
        'description': f'Candidate skill under test: {task["skill"]}',
    }))
    shutil.copytree(skill_src, dest / 'skills' / task['skill'], dirs_exist_ok=True)


def run_once(task, arm_key, models, trial, out_dir: Path, timeout: int):
    arm = ARMS[arm_key]
    model = models[arm['model_role']]
    run_dir = out_dir / arm_key / task['id'] / f'trial-{trial}'
    if (run_dir / 'record.json').exists():
        return json.loads((run_dir / 'record.json').read_text())  # resume: never re-run a finished cell
    ws = run_dir / 'workspace'
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    seed_workspace(task, ws)

    cmd = [
        CLAUDE_BIN, '--print',
        '--setting-sources', '',
        '--strict-mcp-config',
        '--model', model,
        '--permission-mode', 'bypassPermissions',
        '--output-format', 'stream-json', '--verbose',
    ]
    if arm['skill']:
        plug = run_dir / 'plugin'
        build_plugin_dir(task, plug)
        cmd += ['--plugin-dir', str(plug)]

    env = dict(os.environ)
    # A per-run config dir keeps the host's installed skills, settings, memory
    # and session history out of the comparison. Only the OAuth credentials are
    # carried across, because without them the run falls back to a metered API
    # key and this stops being free.
    cfg = run_dir / 'cfg'
    cfg.mkdir(exist_ok=True)
    creds = Path.home() / '.claude' / '.credentials.json'
    if creds.exists():
        shutil.copy2(creds, cfg / '.credentials.json')
        (cfg / '.credentials.json').chmod(0o600)
    env['CLAUDE_CONFIG_DIR'] = str(cfg)

    started = time.time()
    try:
        proc = subprocess.run(
            cmd, input=task['prompt'], cwd=ws, env=env,
            capture_output=True, text=True, timeout=timeout,
        )
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or b'').decode() if isinstance(e.stdout, bytes) else (e.stdout or '')
        stderr = (e.stderr or b'').decode() if isinstance(e.stderr, bytes) else (e.stderr or '')
        rc, timed_out = -1, True

    (run_dir / 'stdout.jsonl').write_text(stdout)
    if stderr.strip():
        (run_dir / 'stderr.txt').write_text(stderr)

    skill_loaded = detect_skill_load(stdout, task['skill'])
    passed, detail = run_check(task, ws, timeout=120)
    infra_reason = detect_infra_error(stdout, stderr, rc, timed_out)

    record = {
        'task': task['id'], 'arm': arm_key, 'trial': trial,
        'model': model, 'skill_available': arm['skill'], 'skill': task['skill'],
        'workflow': task.get('workflow'),
        'passed': bool(passed), 'check_detail': detail,
        'skill_loaded': skill_loaded,
        # A run that crashed, ran out of wall clock, or never reached the model
        # is infrastructure, not a task failure. It is recorded and then
        # excluded, never silently counted as a fail, which would flatter
        # whichever arm crashed less.
        'infra_error': infra_reason is not None,
        'infra_reason': infra_reason,
        'timed_out': timed_out, 'returncode': rc,
        'seconds': round(time.time() - started, 1),
    }
    (run_dir / 'record.json').write_text(json.dumps(record, indent=2))
    return record


#: Phrases that mean the run never became a fair attempt at the task. Matched
#: against the CLI's own result text, which is where these surface.
INFRA_PHRASES = (
    'not logged in', 'please run /login', 'invalid api key', 'authentication',
    'oauth token has expired', 'credit balance is too low', 'rate limit',
    'overloaded', 'service unavailable', 'internal server error',
)


def detect_infra_error(stdout: str, stderr: str, rc: int, timed_out: bool):
    """Why this run should be excluded, or None if it was a fair attempt.

    The subtle case, and the one that silently poisons a whole grid: the CLI
    exits 1 for "Not logged in" exactly as it does for a run that finished and
    simply failed the check. Return code alone cannot tell those apart, so the
    result event has to be read. A whole grid of unauthenticated runs otherwise
    scores as 0% across every arm and looks like a finding.
    """
    if timed_out:
        return 'timed out'
    if rc not in (0, 1):
        return f'runner exited {rc}'

    # The last `type: result` event carries the CLI's own verdict on the run.
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get('type') != 'result':
            continue
        text = str(ev.get('result') or '').lower()
        reason = str(ev.get('terminal_reason') or ev.get('subtype') or '').lower()
        if reason in ('api_error', 'error_during_execution', 'auth_error'):
            return f'{reason}: {text[:120]}' if text else reason
        if ev.get('is_error') and any(p in text for p in INFRA_PHRASES):
            return text[:120]
        # A real attempt reaches the model at least once. Zero turns with an
        # error means the request never landed.
        if ev.get('is_error') and not ev.get('num_turns'):
            return f'no turns completed: {text[:120]}'
        break
    else:
        # No result event at all: the CLI died before it could report.
        blob = (stdout + ' ' + stderr).lower()
        if any(p in blob for p in INFRA_PHRASES):
            return next(p for p in INFRA_PHRASES if p in blob)
        if not stdout.strip():
            return 'runner produced no output'
    return None


def detect_skill_load(stream_json: str, skill: str):
    """Did the agent actually reach the skill? Read it off the tool calls.

    Returns True/False, or None when the transcript is unreadable, because
    'we could not tell' is not the same claim as 'it did not load'.
    """
    if not stream_json.strip():
        return None
    seen_any = False
    for line in stream_json.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        seen_any = True
        if ev.get('type') != 'assistant':
            continue
        for block in (ev.get('message') or {}).get('content') or ():
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            name = block.get('name')
            inp = block.get('input') or {}
            # The Skill tool is the direct signal.
            if name == 'Skill' and skill in str(inp.get('skill') or ''):
                return True
            # Reading SKILL.md by hand counts too: the agent reached the content,
            # which is what the arm is actually testing.
            if name in ('Read', 'Bash') and 'SKILL.md' in str(inp) and skill in str(inp):
                return True
    return False if seen_any else None


def run_check(task, ws: Path, timeout: int):
    """Deterministic verifier. It sees the workspace, never the arm."""
    try:
        proc = subprocess.run(
            [sys.executable, str(task['dir'] / 'check.py'), str(ws)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, 'check timed out'
    return proc.returncode == 0, (proc.stdout or proc.stderr or '').strip()[:800]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--tasks', type=Path, default=ROOT / 'tasks')
    ap.add_argument('--base-model', default='claude-haiku-4-5-20251001')
    ap.add_argument('--strong-model', default='claude-sonnet-5')
    ap.add_argument('--trials', type=int, default=3)
    ap.add_argument('--arms', default='A,B,C,D')
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--seed', type=int, default=20260918)
    ap.add_argument('--claude-bin', default=None,
                    help='path to the real CLI; defaults to the first non-wrapper on PATH')
    a = ap.parse_args()

    global CLAUDE_BIN
    CLAUDE_BIN = resolve_claude_bin(a.claude_bin)
    models = {'base': a.base_model, 'strong': a.strong_model}
    tasks = load_tasks(a.tasks, a.only)
    if not tasks:
        raise SystemExit('no tasks found')
    arm_keys = [k.strip() for k in a.arms.split(',') if k.strip()]

    jobs = [(t, k, n) for t in tasks for k in arm_keys for n in range(1, a.trials + 1)]
    random.Random(a.seed).shuffle(jobs)

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'grid.json').write_text(json.dumps({
        'models': models, 'trials': a.trials, 'arms': arm_keys,
        'tasks': [t['id'] for t in tasks], 'seed': a.seed,
        'claude_bin': CLAUDE_BIN, 'workers': a.workers,
        'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }, indent=2))

    # Runs are independent and mostly spent waiting on the API, so a thread pool
    # turns a six-hour grid into a one-hour one. Keep the pool modest: too many
    # concurrent agents and the runs start contending for memory, which shows up
    # as timeouts and gets scored as infrastructure noise.
    done = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(run_once, t, k, models, n, a.out, a.timeout): (t, k, n)
                   for t, k, n in jobs}
        for fut in as_completed(futures):
            t, k, n = futures[fut]
            try:
                rec = fut.result()
                flag = 'INFRA' if rec['infra_error'] else ('pass' if rec['passed'] else 'fail')
                secs = rec['seconds']
            except Exception as e:  # a crashed runner is infrastructure, not a task failure
                flag, secs = f'ERROR {e}', 0
            with lock:
                done += 1
                print(f'[{done}/{len(jobs)}] {k} {t["id"]} t{n} {flag} {secs}s', flush=True)


if __name__ == '__main__':
    main()
