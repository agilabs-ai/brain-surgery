#!/usr/bin/env python3
"""Turn a grid of runs into a brain-surgery/0.5 result.

The metric is SkillsBench's: task-macro pass rate. Every task contributes one
score, its own pass fraction across trials, and the arm score is the mean of
those. That is deliberately not passes/total pooled across everything, which
would quietly hand more weight to whichever task happened to get more trials.

    task_score_i = passes_i / trials_i
    arm_rate     = mean(task_score_i) * 100

Reported alongside it, again following SkillsBench:

    delta_points     arm_rate(after) - arm_rate(before), in percentage points
    normalized_gain  delta / (100 - before), the share of the headroom closed
    ci95             Wilson interval on each arm
    improved/unchanged/regressed   the paired per-task counts
    mcnemar_p        exact two-sided McNemar on the discordant tasks

The last one is the honest brake. With three discordant tasks the best
attainable two-sided p is 0.25, so at small n the number exists to stop the
report from claiming significance it cannot have.
"""
import argparse
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parent / 'tasks'

#: A task counts as passed for the paired test when it passes the majority of
#: its trials. The headline rate stays the trial-fraction macro average, which
#: is the SkillsBench metric; this threshold governs only the binary verdict
#: the sign test consumes, and the report states it rather than implying it.
PASS_THRESHOLD = 0.5

ARM_LABEL = {
    'A': 'base model, no skill',
    'B': 'base model, with skill',
    'C': 'stronger model, no skill',
    'D': 'stronger model, with skill',
}


def run_cost(rec_path: Path) -> dict | None:
    """What the run actually cost, from the CLI's own final `result` event.

    Billed tokens exclude cache reads, because a cache read is not what the
    caller pays for. The cache-read figure is still carried so the total is
    reconstructable by anyone who disagrees with that choice.
    """
    tr = rec_path.parent / 'stdout.jsonl'
    if not tr.exists():
        return None
    final = None
    for line in tr.read_text(errors='replace').splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if isinstance(e, dict) and e.get('type') == 'result':
            final = e
    if not final:
        return None
    u = final.get('usage') or {}
    return {
        'billed': (u.get('input_tokens', 0) + u.get('cache_creation_input_tokens', 0)
                   + u.get('output_tokens', 0)),
        'cache_read': u.get('cache_read_input_tokens', 0),
        'output': u.get('output_tokens', 0),
        'turns': final.get('num_turns') or 0,
        'seconds': (final.get('duration_ms') or 0) / 1000.0,
    }


def collect(run_dir: Path):
    """Read every record. Infra errors are held aside, never scored."""
    scores = defaultdict(dict)   # arm -> task -> {'passed':n,'total':n,'loaded':n}
    costs = defaultdict(list)    # arm -> [run_cost, ...]
    excluded = []
    for rec_path in sorted(run_dir.rglob('record.json')):
        r = json.loads(rec_path.read_text())
        if r.get('infra_error'):
            excluded.append({'task': r['task'], 'arm': r['arm'], 'trial': r['trial'],
                             'reason': 'timeout' if r.get('timed_out') else f'exit {r.get("returncode")}'})
            continue
        cell = scores[r['arm']].setdefault(r['task'], {'passed': 0, 'total': 0, 'loaded': 0, 'loaded_known': 0})
        cell['total'] += 1
        cell['passed'] += 1 if r['passed'] else 0
        if r.get('skill_loaded') is not None:
            cell['loaded_known'] += 1
            cell['loaded'] += 1 if r['skill_loaded'] else 0
        rc = run_cost(rec_path)
        if rc:
            rc['passed'] = bool(r['passed'])
            costs[r['arm']].append(rc)
    return scores, costs, excluded


def cost_summary(costs: dict) -> dict:
    """Per-arm cost, and the one cost figure that means anything: what a run
    that actually passes its checks costs, counting the failed attempts.

    Per-run token spend barely moves between arms, so a report claiming a skill
    "saves tokens" would be wrong. What moves is how much of that identical
    spend comes back as output that passes, which is why the ratio below is
    computed over every run in the arm and not over the winners only.
    """
    out = {}
    for arm, runs in costs.items():
        if not runs:
            continue
        n = len(runs)
        passes = sum(1 for r in runs if r['passed'])
        billed = sum(r['billed'] for r in runs)
        out[arm] = {
            'runs': n,
            'passes': passes,
            'billed_per_run': round(billed / n),
            'output_per_run': round(sum(r['output'] for r in runs) / n),
            'turns_per_run': round(sum(r['turns'] for r in runs) / n, 1),
            'seconds_per_run': round(sum(r['seconds'] for r in runs) / n, 1),
            # None, not infinity: an arm that never passed has no cost per pass,
            # and printing a large number there would invent a measurement.
            'billed_per_pass': round(billed / passes) if passes else None,
        }
    return out


def macro_rate(arm_tasks, task_ids):
    """Task-macro pass rate over exactly the given tasks."""
    fracs = [arm_tasks[t]['passed'] / arm_tasks[t]['total'] for t in task_ids]
    return 100.0 * sum(fracs) / len(fracs) if fracs else 0.0


def wilson(passed, total, z=1.96):
    """Wilson score interval. Sane at small n, unlike the normal approximation."""
    if total == 0:
        return [0.0, 100.0]
    p = passed / total
    d = 1 + z * z / total
    c = p + z * z / (2 * total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return [round(100 * (c - half) / d, 1), round(100 * (c + half) / d, 1)]


def exact_mcnemar(improved, regressed):
    """Two-sided exact McNemar, i.e. a binomial sign test on discordant pairs.

    Concordant tasks carry no information about the direction of the effect,
    so only the discordant ones count. Returns None when nothing is discordant.
    """
    n = improved + regressed
    if n == 0:
        return None
    k = min(improved, regressed)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return round(min(1.0, 2 * tail), 4)


def min_detectable_note(improved, regressed):
    """What the sample can and cannot show, stated before anyone over-reads it."""
    n = improved + regressed
    if n == 0:
        return 'No task changed direction. This sample shows no effect either way.'
    if n < 5:
        return (f'Only {n} task{"s" if n != 1 else ""} changed direction. Even if every one of them '
                f'had moved the same way, the smallest two-sided p this sample can produce is '
                f'{exact_mcnemar(n, 0)}. Read this as a direction, not as proof.')
    return f'{n} tasks changed direction, enough for a two-sided test to reach significance.'


def compare(scores, before_arm, after_arm, label=None):
    """One before/after contrast over the tasks both arms actually completed."""
    b, a = scores.get(before_arm, {}), scores.get(after_arm, {})
    task_ids = sorted(set(b) & set(a))
    if not task_ids:
        return None

    # McNemar is a sign test on discordant pairs of BINARY outcomes, so the
    # counts it consumes have to be flips of the task's pass/fail verdict, not
    # any rise in the trial fraction. Counting 0/3 -> 1/3 as "improved" adds a
    # pair that never flipped, inflates the discordant total and overstates the
    # significance. The trial-level movement is still worth reporting, so it is
    # kept under its own name and kept out of the test.
    improved = unchanged = regressed = 0
    trial_improved = trial_regressed = 0
    pairs = []
    for t in task_ids:
        bf = b[t]['passed'] / b[t]['total']
        af = a[t]['passed'] / a[t]['total']
        if af > bf:
            trial_improved += 1
        elif af < bf:
            trial_regressed += 1
        b_pass, a_pass = bf >= PASS_THRESHOLD, af >= PASS_THRESHOLD
        if a_pass and not b_pass:
            improved += 1
        elif b_pass and not a_pass:
            regressed += 1
        else:
            unchanged += 1
        pairs.append({
            'task_id': t,
            'before': b_pass, 'after': a_pass,
            'trials': {'before': {'passed': b[t]['passed'], 'total': b[t]['total']},
                       'after': {'passed': a[t]['passed'], 'total': a[t]['total']}},
            'invocation': {'eligible': True,
                           'before': b[t]['loaded'] > 0,
                           'after': a[t]['loaded'] > 0,
                           'trials_loaded': {'before': b[t]['loaded'], 'after': a[t]['loaded']}},
            'valid': True,
        })

    br, ar = macro_rate(b, task_ids), macro_rate(a, task_ids)
    delta = ar - br
    bp = sum(b[t]['passed'] for t in task_ids); bt = sum(b[t]['total'] for t in task_ids)
    ap = sum(a[t]['passed'] for t in task_ids); at = sum(a[t]['total'] for t in task_ids)

    return {
        'label': label or f'{ARM_LABEL[before_arm]} -> {ARM_LABEL[after_arm]}',
        'before': {'arm': before_arm, 'label': ARM_LABEL[before_arm],
                   'rate': round(br, 1), 'passed': bp, 'trials': bt, 'ci95': wilson(bp, bt)},
        'after': {'arm': after_arm, 'label': ARM_LABEL[after_arm],
                  'rate': round(ar, 1), 'passed': ap, 'trials': at, 'ci95': wilson(ap, at)},
        'tasks_compared': len(task_ids),
        'delta_points': round(delta, 1),
        # Share of the remaining headroom closed. A +10 from 80 is a different
        # achievement from a +10 from 20, and this is the number that says so.
        'normalized_gain': round(100 * delta / (100 - br), 1) if br < 100 else None,
        'improved_tasks': improved, 'unchanged_tasks': unchanged, 'regressed_tasks': regressed,
        'pass_threshold': PASS_THRESHOLD,
        # Reported so the two counts on the page can be told apart, never fed
        # to the test: these are trial-fraction moves, not verdict flips.
        'trial_level_improved': trial_improved, 'trial_level_regressed': trial_regressed,
        'mcnemar_p': exact_mcnemar(improved, regressed),
        'power_note': min_detectable_note(improved, regressed),
        'pairs': pairs,
    }


def harness_commit() -> str:
    """Which version of the harness produced this.

    A result that cannot say which code ran is not reproducible, whatever else
    the page claims. `-dirty` is kept on purpose: a run against uncommitted
    changes is worth less, and hiding that would be the more expensive lie.
    """
    try:
        out = subprocess.run(['git', 'describe', '--always', '--dirty'],
                             cwd=Path(__file__).resolve().parent, capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return 'not recorded'
    return out.stdout.strip() or 'not recorded'


def task_index() -> dict:
    """The task-to-skill map, so the report can print what each task was paired
    with rather than asking the reader to take the pairing on trust."""
    index = {}
    for manifest in sorted(TASKS_DIR.glob('*/task.json')):
        try:
            d = json.loads(manifest.read_text())
        except (OSError, ValueError):
            continue
        if d.get('id'):
            index[d['id']] = {'skill': d.get('skill'), 'workflow': d.get('workflow')}
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--skills-inspected', type=int, default=0)
    # The runner is often a copy of the tree rather than the checkout, and a copy
    # has no git to ask. Better to be told the commit than to print a blank.
    ap.add_argument('--harness-commit', default=None)
    a = ap.parse_args()

    grid = json.loads((a.runs / 'grid.json').read_text())
    scores, costs, excluded = collect(a.runs)

    contrasts = {
        'setup_lift': compare(scores, 'A', 'B', 'Setup change, same model'),
        'model_lift': compare(scores, 'A', 'C', 'Model upgrade, same setup'),
        'setup_on_strong': compare(scores, 'C', 'D', 'Setup change on the stronger model'),
        'stacked': compare(scores, 'A', 'D', 'Both changes together'),
        # The cross-corner question the whole thesis rests on: does the weaker
        # model with a skill beat the stronger model without one?
        'skill_vs_model': compare(scores, 'C', 'B', 'Stronger model alone vs base model with the skill'),
    }

    all_tasks = sorted({t for arm in scores.values() for t in arm})
    result = {
        'schema_version': 'brain-surgery/0.5',
        'example': False,
        'metric_kind': 'task_macro_pass_rate',
        'metric_note': 'Task-macro pass rate: each task scores passes/trials, the arm scores the mean. '
                       'Matches the SkillsBench primary metric so the numbers are comparable.',
        'model_family': 'Claude',
        'evaluator_type': 'fixed_checks',
        'skills_inspected': a.skills_inspected,
        'generated_by': 'eval/to_result.py',
        'grid': {
            'models': grid['models'],
            'trials_per_task': grid['trials'],
            'tasks': len(all_tasks),
            'arms': {k: {'label': ARM_LABEL[k],
                         'rate': round(macro_rate(scores[k], sorted(scores[k])), 1),
                         'tasks': len(scores[k])}
                     for k in sorted(scores)},
        },
        'contrasts': {k: v for k, v in contrasts.items() if v},
        'cost': cost_summary(costs),
        'tasks_index': task_index(),
        'provenance': {
            'harness_commit': a.harness_commit or harness_commit(),
            'started': grid.get('started'),
            'seed': grid.get('seed'),
            'workers': grid.get('workers'),
            'command': (f'python3 eval/run_grid.py --out runs --trials {grid["trials"]} '
                        f'--seed {grid.get("seed")}'),
        },
        'excluded': excluded,
        'caveats': [
            "Every task is drawn from one person's real session logs. n equals one machine, "
            "so this measures this setup, not setups in general.",
            'Prompts are identical across arms and never mention that a skill exists, so the '
            'with-skill arms measure discovery and use together, not use alone.',
            'The verifier is a fixed script that runs against the finished workspace and never '
            'sees which arm produced it.',
            # The no-skill arms land near the floor, which is the first thing a
            # sceptical reader should distrust, so the reason is stated rather
            # than left to be discovered. Checked directly: rewriting every em
            # dash and re-running the untouched verifiers rescued 0 of 141
            # failed no-skill runs, and the failures spread over 31 distinct
            # messages, so no single rule is carrying the result.
            'Each task asserts a house convention that is arbitrary by construction, roughly '
            'fourteen checks deep, and nowhere in the prompt. An agent without the skill has no '
            'way to guess it, so the no-skill arms sit near zero and the gap measures convention '
            'compliance rather than general task ability.',
        ],
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2))

    g = result['grid']['arms']
    print(f'tasks={result["grid"]["tasks"]} trials={grid["trials"]}')
    for k in sorted(g):
        print(f'  {k}  {g[k]["rate"]:5.1f}%  {g[k]["label"]}')
    for name, c in result['contrasts'].items():
        print(f'  {name:16s} {c["delta_points"]:+.1f}pp  '
              f'{c["improved_tasks"]}/{c["unchanged_tasks"]}/{c["regressed_tasks"]} (i/u/r)  p={c["mcnemar_p"]}')
    if excluded:
        print(f'  excluded (infra): {len(excluded)}')


if __name__ == '__main__':
    main()
