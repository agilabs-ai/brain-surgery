#!/usr/bin/env python3
# provenance: shape `video-storyboard-then-render`, seen in 6 sessions.
# Hard rules cited: HR-8 (text is never animated by moving it),
#                   storyboard-first ordering from the same shape.
"""Verifier for storyboard-before-render.

Two things are checked: the storyboard exists and was finished before the render
plan was written (file mtimes), and no text node in the plan is animated by
moving it.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

MOVE_KEYS = {'translatex', 'translatey', 'translate', 'x', 'y', 'left', 'top',
             'offsetx', 'offsety', 'posx', 'posy'}
# `at`/`position`/`origin` place a node; they are not motion. Only animation
# tracks count as movement.
ANIM_KEYS = {'animate', 'animation', 'animations', 'keyframes', 'tracks',
             'transition', 'transitions', 'motion', 'enter', 'exit', 'in', 'out'}


def norm(s):
    return ' '.join(s.split())


def find_plan(ws: Path, brief_ids):
    cands = []
    for p in sorted(ws.rglob('*.json')):
        if p.name == 'brief.json' or 'examples' in p.relative_to(ws).parts:
            continue
        try:
            data = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get('scenes'), list) and data['scenes']:
            if any(isinstance(s, dict) and 'nodes' in s for s in data['scenes']):
                cands.append((p, data))
    if not cands:
        return None, None
    for p, d in cands:
        if [s.get('id') for s in d['scenes']] == brief_ids:
            return p, d
    return cands[0]


def moving_tracks(obj):
    """Yield the animation keys under obj that move the node."""
    found = []

    def walk(node, in_anim):
        if isinstance(node, dict):
            for k, v in node.items():
                lk = str(k).lower()
                if in_anim and lk in MOVE_KEYS:
                    found.append(lk)
                walk(v, in_anim or lk in ANIM_KEYS)
        elif isinstance(node, list):
            for v in node:
                walk(v, in_anim)

    walk(obj, False)
    return found


def iter_nodes(obj):
    if isinstance(obj, dict):
        if str(obj.get('type', '')).lower() in ('text', 'caption', 'headline', 'title', 'subtitle'):
            yield obj
        for v in obj.values():
            yield from iter_nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_nodes(v)


def main():
    ws = Path(sys.argv[1])

    # The brief, the storyboard and the plan are all resolved up front so a
    # missing one fails its own sections instead of stopping the verifier.
    bf = ws / 'brief.json'
    try:
        brief = json.loads(bf.read_text())
        scenes = brief['scenes']
    except Exception:
        scenes = []
    brief_ids = [s['id'] for s in scenes]

    boards = [p for p in sorted(ws.rglob('*.html')) if p.is_file()]
    board = min(boards, key=lambda p: p.stat().st_mtime_ns) if boards else None
    plan_path, plan = find_plan(ws, brief_ids)

    # Outcome: brief.json is the input the prompt names, and a readable brief is
    # what the work is built from; losing or corrupting it is the real failure.
    with section('brief-intact', 'outcome'):
        if not bf.exists():
            fail('brief.json missing from the workspace')
        if not scenes:
            fail('brief.json no longer parses into a scene list; it is the input and is left alone')

    # Convention: the prompt asks for a render plan and never mentions a
    # storyboard at all, so storyboard-first is knowable only from the skill.
    with section('storyboard-covers-every-scene', 'convention'):
        if not scenes:
            fail('no readable brief.json to check the storyboard against')
        if board is None:
            fail('no storyboard HTML anywhere in the workspace; the render plan was built without one')
        bhtml = board.read_text(encoding='utf-8', errors='replace')
        bflat = norm(bhtml)
        for s in scenes:
            if s['id'] not in bhtml:
                fail(f'storyboard {board.name} has no card for scene {s["id"]}')
            if norm(s['headline']) not in bflat:
                fail(f'storyboard {board.name} is missing scene {s["id"]} headline {s["headline"]!r}')
            if norm(s['caption']) not in bflat:
                fail(f'storyboard {board.name} is missing scene {s["id"]} caption text')

    # Outcome: "Put together the render plan ... examples/prior-plan.json is the
    # format our renderer takes" is the request, in the prompt, in those words.
    with section('render-plan-produced', 'outcome'):
        if plan is None:
            fail('no render plan JSON was produced (expected a scenes/nodes plan like examples/prior-plan.json)')

    # Outcome: the prompt asks for "the four-scene explainer in brief.json", so
    # a plan whose scenes are not the brief's scenes is the wrong plan.
    with section('plan-scenes-match-brief', 'outcome'):
        if plan is None:
            fail('no render plan JSON to compare against the brief')
        plan_ids = [s.get('id') for s in plan['scenes']]
        if plan_ids != brief_ids:
            fail(f'render plan scenes {plan_ids} do not match the brief {brief_ids}')

    # Outcome: the copy is the content of the job; a plan that drops the brief's
    # headlines has not rendered the explainer that was asked for.
    with section('plan-carries-brief-copy', 'outcome'):
        if plan is None:
            fail('no render plan JSON to read the scene copy from')
        if not scenes:
            fail('no readable brief.json to take the scene copy from')
        blob = json.dumps(plan, ensure_ascii=False)
        for s in scenes:
            if s['headline'] not in blob:
                fail(f'render plan never uses scene {s["id"]} headline {s["headline"]!r}')

    # Convention: HR-8 exists only in the skill, and the seeded format example
    # the prompt points at animates its own text with translateX/translateY, so
    # following the workspace faithfully is what breaks this rule.
    with section('text-is-not-moved', 'convention'):
        if plan is None:
            fail('no render plan JSON to inspect for text motion')
        for scene in plan['scenes']:
            for node in iter_nodes(scene):
                mv = moving_tracks(node)
                if mv:
                    label = node.get('content') or node.get('text') or node.get('role') or '?'
                    fail(f'scene {scene.get("id")}: text node {str(label)[:48]!r} is animated by moving it '
                         f'({sorted(set(mv))})')

    # Convention: the ordering rule, board finished before the plan is written,
    # is the house process; the prompt asks only for the finished plan.
    with section('storyboard-precedes-plan', 'convention'):
        if board is None:
            fail('no storyboard HTML anywhere in the workspace; the render plan was built without one')
        if plan is None:
            fail('no render plan JSON was produced, so nothing can be ordered against the storyboard')
        if board.stat().st_mtime_ns > plan_path.stat().st_mtime_ns:
            fail(f'{board.name} was written after {plan_path.name}; the storyboard has to be finished first')

    emit()


main()
