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

MOVE_KEYS = {'translatex', 'translatey', 'translate', 'x', 'y', 'left', 'top',
             'offsetx', 'offsety', 'posx', 'posy'}
# `at`/`position`/`origin` place a node; they are not motion. Only animation
# tracks count as movement.
ANIM_KEYS = {'animate', 'animation', 'animations', 'keyframes', 'tracks',
             'transition', 'transitions', 'motion', 'enter', 'exit', 'in', 'out'}


def fail(msg):
    print(msg)
    sys.exit(1)


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
    bf = ws / 'brief.json'
    if not bf.exists():
        fail('brief.json missing from the workspace')
    brief = json.loads(bf.read_text())
    scenes = brief['scenes']
    brief_ids = [s['id'] for s in scenes]

    boards = [p for p in sorted(ws.rglob('*.html')) if p.is_file()]
    if not boards:
        fail('no storyboard HTML anywhere in the workspace; the render plan was built without one')
    board = min(boards, key=lambda p: p.stat().st_mtime_ns)
    bhtml = board.read_text(encoding='utf-8', errors='replace')
    bflat = norm(bhtml)
    for s in scenes:
        if s['id'] not in bhtml:
            fail(f'storyboard {board.name} has no card for scene {s["id"]}')
        if norm(s['headline']) not in bflat:
            fail(f'storyboard {board.name} is missing scene {s["id"]} headline {s["headline"]!r}')
        if norm(s['caption']) not in bflat:
            fail(f'storyboard {board.name} is missing scene {s["id"]} caption text')

    plan_path, plan = find_plan(ws, brief_ids)
    if plan is None:
        fail('no render plan JSON was produced (expected a scenes/nodes plan like examples/prior-plan.json)')

    plan_ids = [s.get('id') for s in plan['scenes']]
    if plan_ids != brief_ids:
        fail(f'render plan scenes {plan_ids} do not match the brief {brief_ids}')

    blob = json.dumps(plan, ensure_ascii=False)
    for s in scenes:
        if s['headline'] not in blob:
            fail(f'render plan never uses scene {s["id"]} headline {s["headline"]!r}')

    for scene in plan['scenes']:
        for node in iter_nodes(scene):
            mv = moving_tracks(node)
            if mv:
                label = node.get('content') or node.get('text') or node.get('role') or '?'
                fail(f'scene {scene.get("id")}: text node {str(label)[:48]!r} is animated by moving it '
                     f'({sorted(set(mv))})')

    if board.stat().st_mtime_ns > plan_path.stat().st_mtime_ns:
        fail(f'{board.name} was written after {plan_path.name}; the storyboard has to be finished first')

    print('ok')
    sys.exit(0)


main()
