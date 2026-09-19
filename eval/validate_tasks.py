#!/usr/bin/env python3
"""Structural gate for the task corpus.

Four agents author tasks independently, so nothing downstream should assume they
agreed. This checks the contract in TASK_SPEC.md across every task at once and
refuses rather than repairs: a task that fails here is a task whose numbers would
be meaningless, and a meaningless number in a report is worse than a missing one.

The expensive check is the leak check. A prompt that names the convention the
verifier tests turns a benchmark task into an instruction-following task, which
every arm passes. That failure is invisible in the results (it looks like a tie),
so it has to be caught here or not at all.

Usage:  python3 eval/validate_tasks.py [--verbose]
Exit 0 if every task is shippable, 1 otherwise.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / 'tasks'
SKILLS = ROOT / 'skills'

WORKFLOWS = {'writing', 'coding', 'research', 'design',
             'presentations', 'spreadsheets', 'other'}

#: Anything that reaches the network or the clock makes a verifier
#: non-deterministic, which breaks the paired comparison the stats rest on.
FORBIDDEN_IMPORTS = {'requests', 'urllib', 'http', 'socket', 'random',
                     'datetime', 'time', 'subprocess', 'anthropic', 'openai'}

#: Words that would drag a real product into a synthetic benchmark. The tasks are
#: modelled on his workflows, not his companies, and the report is going public.
BRANDING = ['getedge', 'edge.cc', 'floom', 'rocketlist', 'signaldash', 'gopaula',
            'reltix', 'uplane', 'workeros', 'agilabs', 'brain surgery', 'skillsbench']

#: Tokens too generic to mean a leak on their own. Checked against the prompt only
#: after the skill's own distinctive vocabulary has been extracted.
STOPWORDS = set('''a an and are as at be but by can do does for from has have how if in into is it
its no not of on one or so than that the their them then there these they this to use used uses was
what when where which who will with would you your file files write writes written line lines text
word words name names value values list only every each all any some more most must never always
should keep make made put set get run runs page post note notes json md markdown html css'''.split())


class Problem(Exception):
    pass


def frontmatter(md: str) -> dict:
    """Parse the YAML header without a YAML dependency. Only flat scalars are
    legal in a SKILL.md header, so a two-key reader is honest rather than lazy."""
    if not md.startswith('---'):
        raise Problem('SKILL.md has no frontmatter block')
    end = md.find('\n---', 3)
    if end < 0:
        raise Problem('SKILL.md frontmatter is not terminated')
    out = {}
    for line in md[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            raise Problem(f'unparseable frontmatter line: {line!r}')
        k, v = line.split(':', 1)
        out[k.strip()] = v.strip().strip('"\'')
    return out


#: A path or filename in the prompt is not a leak. The prompt has to say where the
#: output goes, or the verifier cannot find the artifact and every arm fails for
#: the wrong reason. What must not leak is the CONVENTION: the values, keys and
#: limits the verifier asserts once it has opened that file.
FILENAME = re.compile(r'^[\w.\-]+\.(md|json|html|css|js|py|txt|csv|svg|png|yaml|yml)$')


def distinctive(skill_md: str) -> set[str]:
    """The vocabulary that encodes the convention itself.

    Three things qualify, and nothing else does. A JSON key the verifier reads
    (`dueAt`), a literal value it compares against (`"scheduled"`), and a numeric
    limit it enforces (`150 to 180 words`). A bare English word in backticks is
    formatting, and a filename is an address rather than a rule.
    """
    out: set[str] = set()
    for raw in re.findall(r'`([^`\n]{2,40})`', skill_md):
        t = raw.strip().strip('.,:;()[]{}').lower()
        if not t or FILENAME.match(t) or '/' in t:
            continue
        words = t.split()
        camel = re.fullmatch(r'[a-z]+[A-Z]\w*', raw.strip())
        # Multi-word phrases and camelCase keys are conventions. A lone lowercase
        # word is only a convention if it carries a digit or is not ordinary English.
        if camel or len(words) > 1 or any(c.isdigit() for c in t):
            if t not in STOPWORDS:
                out.add(t)
        elif len(t) >= 6 and t not in STOPWORDS:
            out.add(t)
    # Numeric limits stated in prose ("150 to 180 words", "at least six paragraphs").
    for m in re.findall(r'\b(\d{2,4}\s*(?:to|-|and)\s*\d{2,4}\s+\w+)', skill_md.lower()):
        out.add(m.strip())
    return out


def check_verifier(path: Path) -> list[str]:
    """Static checks on check.py. It is never executed here: running an unreviewed
    verifier against an empty directory tells you nothing a parse does not."""
    src = path.read_text(encoding='utf-8')
    notes = []
    if not re.search(r'^#\s*provenance:', src, re.M):
        notes.append('check.py has no `# provenance:` comment (TASK_SPEC requires the shape and session count)')
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return notes + [f'check.py does not parse: line {e.lineno}: {e.msg}']

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
    bad = imported & FORBIDDEN_IMPORTS
    if bad:
        notes.append(f'check.py imports {sorted(bad)}, which makes it non-deterministic')

    # A verifier that can only ever exit 0 passes a blank workspace.
    #
    # Two shapes are legal. The original one calls sys.exit directly. The migrated
    # one hands control to checklib, which runs every section, prints the per-check
    # JSON and then exits non-zero if any section failed. For that shape the exit
    # lives in checklib, so looking for a literal sys.exit here would condemn every
    # migrated task, which is exactly what happened the first time this ran after
    # the migration. The equivalent guarantee is checked instead: it must call
    # report(), and it must record at least one section that can fail.
    calls = {n for n in ast.walk(tree) if isinstance(n, ast.Call)}
    names = {getattr(c.func, 'id', '') or getattr(c.func, 'attr', '') for c in calls}
    uses_checklib = any(
        (isinstance(n, ast.ImportFrom) and (n.module or '') == 'checklib')
        or (isinstance(n, ast.Import) and any(a.name == 'checklib' for a in n.names))
        for n in ast.walk(tree))

    if uses_checklib:
        # `report` is imported as `emit` by convention, so accept either name.
        if not ({'emit', 'report'} & names):
            notes.append('check.py imports checklib but never calls report(); '
                         'nothing would print the per-check result or set the exit code')
        sections = sum(1 for n in ast.walk(tree)
                       for item in getattr(n, 'items', [])
                       if isinstance(getattr(item, 'context_expr', None), ast.Call)
                       and getattr(item.context_expr.func, 'id', '') == 'section')
        if not sections:
            notes.append('check.py imports checklib but declares no section(), '
                         'so it records nothing and can only ever pass')
        elif 'fail' not in names:
            notes.append('check.py declares sections but never calls fail(), '
                         'so every section passes unconditionally')
        return notes

    exits = {ast.unparse(n.args[0]) if n.args else '0'
             for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'exit'
             or isinstance(n, ast.Call) and getattr(getattr(n.func, 'attr', None) and n.func, 'attr', '') == 'exit'}
    if not exits or exits <= {'0'}:
        notes.append('check.py never exits non-zero, so it can only ever pass')
    return notes


def validate(task_dir: Path, seen_ids: set, verbose: bool) -> list[str]:
    tid = task_dir.name
    errs: list[str] = []
    tj = task_dir / 'task.json'
    chk = task_dir / 'check.py'
    if not tj.exists():
        return ['task.json missing']
    if not chk.exists():
        errs.append('check.py missing')

    try:
        spec = json.loads(tj.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        return [f'task.json is not valid JSON: {e}']

    for key in ('id', 'workflow', 'skill', 'prompt'):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            errs.append(f'task.json missing or empty `{key}`')
    if errs:
        return errs

    if spec['id'] != tid:
        errs.append(f'task.json id {spec["id"]!r} does not match directory {tid!r}')
    if spec['id'] in seen_ids:
        errs.append(f'duplicate task id {spec["id"]!r}')
    seen_ids.add(spec['id'])
    smoke = bool(spec.get('smoke'))
    if spec['workflow'] not in WORKFLOWS:
        errs.append(f'workflow {spec["workflow"]!r} is not one of {sorted(WORKFLOWS)}')

    skill_dir = SKILLS / spec['skill']
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
        errs.append(f'skill {spec["skill"]!r} has no SKILL.md at {skill_md}')
        return errs

    md = skill_md.read_text(encoding='utf-8')
    try:
        fm = frontmatter(md)
    except Problem as e:
        errs.append(str(e))
        fm = {}
    if fm.get('name') and fm['name'] != spec['skill']:
        errs.append(f'SKILL.md name {fm["name"]!r} does not match directory {spec["skill"]!r}')
    if not fm.get('description'):
        errs.append('SKILL.md has no description, so the agent has nothing to decide on')
    elif len(fm['description']) < 40:
        errs.append('SKILL.md description is too short to name a trigger situation')

    prompt = spec['prompt']
    low = prompt.lower()

    # The leak check, in three widening passes.
    if spec['skill'].lower() in low:
        errs.append('prompt names the skill directly')
    for word in ('skill', 'skill.md', 'convention', 'house style', 'the rules say'):
        if word in low:
            errs.append(f'prompt contains {word!r}, which tells the agent a skill exists')
    # Anything already present in the materials the agent is handed cannot be a
    # secret, so the prompt repeating it costs nothing. Build that context first
    # and subtract it, rather than second-guessing each hit by hand.
    context = ' '.join(list((spec.get('seed') or {}).keys()) +
                       [str(v) for v in (spec.get('seed') or {}).values()]).lower()
    ws = task_dir / 'workspace'
    if ws.exists():
        for p in ws.rglob('*'):
            if p.is_file():
                context += ' ' + p.name.lower()
                try:
                    context += ' ' + p.read_text(encoding='utf-8', errors='ignore').lower()
                except OSError:
                    pass
    # The description is deliberately written in the words the prompt would use,
    # because that is how the agent finds the skill at all. Trigger vocabulary
    # appearing in both is the design working, not the secret escaping.
    trigger = (fm.get('description') or '').lower()
    leaks = sorted(t for t in distinctive(md)
                   if t in low and t not in context and t not in trigger)
    if leaks:
        errs.append(f'prompt leaks skill vocabulary {leaks[:6]}')

    for b in BRANDING:
        if b in low or b in md.lower():
            errs.append(f'real-world branding {b!r} appears in the task or skill')

    if re.search(r'[—–]|&mdash;|&ndash;', prompt):
        errs.append('prompt contains an em or en dash')

    if chk.exists():
        notes = check_verifier(chk)
        # A smoke task is a harness check, not a graded one. It is never scored,
        # so provenance and calibration do not apply to it.
        if smoke:
            notes = [n for n in notes if 'provenance' not in n]
        errs += notes

    has_ws = (task_dir / 'workspace').exists()
    if not has_ws and not spec.get('seed') and not smoke:
        errs.append('task has neither workspace/ nor seed, so the agent starts from nothing')

    if verbose and not errs:
        n = len(list((task_dir / 'workspace').rglob('*'))) if has_ws else len(spec.get('seed') or {})
        print(f'  ok  {tid:28s} {spec["workflow"]:14s} {spec["skill"]:26s} {n} seeded')
    return errs


def main() -> int:
    verbose = '--verbose' in sys.argv
    dirs = sorted(p for p in TASKS.iterdir() if p.is_dir())
    if not dirs:
        print('no tasks found', file=sys.stderr)
        return 1

    seen: set = set()
    failed = {}
    for d in dirs:
        errs = validate(d, seen, verbose)
        if errs:
            failed[d.name] = errs

    used_skills = set()
    for d in dirs:
        try:
            used_skills.add(json.loads((d / 'task.json').read_text())['skill'])
        except Exception:
            pass
    orphans = sorted({p.name for p in SKILLS.iterdir() if p.is_dir()} - used_skills)

    print(f'\n{len(dirs)} tasks, {len(used_skills)} skills in use, {len(failed)} failing')
    if orphans:
        print(f'{len(orphans)} skills no task exercises: {", ".join(orphans)}')
    for tid, errs in sorted(failed.items()):
        print(f'\n  {tid}')
        for e in errs:
            print(f'    - {e}')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
