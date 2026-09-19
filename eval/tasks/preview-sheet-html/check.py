#!/usr/bin/env python3
# provenance: shape `html-preview-for-review`, seen in 9 sessions.
# Hard rules cited: HR-13 (never regenerate an asset that already exists),
#                   HR-1  (no em dashes, in any encoding).
"""Verifier for preview-sheet-html.

One scrollable HTML sheet, one card per scene, each card showing the still that
already exists on disk, and none of the source em dashes carried through.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
SPLIT = re.compile(r'[—–]|&mdash;|&#8212;|&#x2014;')


def norm(s):
    return ' '.join(s.split())


def main():
    ws = Path(sys.argv[1])
    src = ws / 'scenes.json'

    # The source and the sheet are both read outside the sections, so a missing
    # scenes.json fails every check that needs it explicitly instead of letting
    # a loop over an empty scene list pass for free.
    scenes = []
    scenes_error = None
    if not src.exists():
        scenes_error = 'scenes.json missing from the workspace'
    else:
        try:
            scenes = json.loads(src.read_text())['scenes']
        except Exception as e:
            scenes_error = f'scenes.json could not be read: {type(e).__name__}: {e}'

    sheets = sorted(p for p in ws.rglob('*.html') if p.is_file())
    sheet = sheets[0] if sheets else None
    html = sheet.read_text(encoding='utf-8', errors='replace') if sheet else ''
    flat = norm(html)

    # Outcome: scenes.json is the input the prompt points at; it is still needed
    # after the sheet is built and destroying it is the real failure mode.
    with section('scenes-source-intact', 'outcome'):
        if scenes_error:
            fail(scenes_error)

    # Outcome: "put them on one HTML sheet I can scroll through" is the request,
    # in the prompt, in those words.
    with section('one-html-sheet', 'outcome'):
        if not sheets:
            fail('no .html sheet was produced anywhere in the workspace')
        if len(sheets) > 1:
            names = sorted(str(p.relative_to(ws)) for p in sheets)
            fail(f'expected one sheet with all {len(scenes)} scenes, found {len(sheets)}: {names}')

    # Convention: HR-1. The prompt says nothing about punctuation, and the em
    # dashes come straight out of the seeded voiceover copy.
    with section('no-em-dash', 'convention'):
        if sheet is None:
            fail('no sheet to check for em dashes')
        m = DASH.search(html)
        if m:
            i = m.start()
            fail(f'em/en dash in {sheet.name} at offset {i}: ...{html[max(0, i - 45):i + 45]!r}')

    # Every scene present, in full.
    # Outcome: the prompt asks to look at "the five scenes in scenes.json"
    # properly, so a sheet missing a scene is the wrong deliverable.
    with section('all-scenes-present', 'outcome'):
        if sheet is None:
            fail('no sheet to look for the scenes in')
        if not scenes:
            fail(scenes_error or 'scenes.json lists no scenes')
        for sc in scenes:
            if sc['id'] not in html:
                fail(f'scene id {sc["id"]!r} is not in {sheet.name}')
            if norm(sc['title']) not in flat:
                fail(f'scene {sc["id"]} title {sc["title"]!r} is not in {sheet.name}')

    # Outcome: "look at them properly" means the real copy, not a paraphrase;
    # silently rewording the voiceover defeats the review the prompt asks for.
    with section('voiceover-verbatim', 'outcome'):
        if sheet is None:
            fail('no sheet to look for the voiceover in')
        if not scenes:
            fail(scenes_error or 'scenes.json lists no scenes')
        for sc in scenes:
            for frag in SPLIT.split(sc['voiceover']):
                frag = norm(frag).strip(' .,')
                if len(frag) < 12:
                    continue
                if frag not in flat:
                    fail(f'scene {sc["id"]} voiceover text is missing or was reworded: {frag!r}')

    # Every card shows the still that already exists, referenced by a resolving
    # relative path. Re-drawn placeholders and inline shapes do not count.
    # Convention: HR-13. The prompt never mentions stills/ at all, so reusing
    # the existing SVGs rather than drawing placeholders is skill-only.
    with section('uses-existing-stills', 'convention'):
        if sheet is None:
            fail('no sheet to show the existing stills on')
        if not scenes:
            fail(scenes_error or 'scenes.json lists no scenes')
        srcs = re.findall(r'<img[^>]*\ssrc\s*=\s*["\']([^"\']+)["\']', html, re.I)
        if not srcs:
            fail(f'{sheet.name} has no <img> at all; the existing stills were not used')
        resolved = set()
        for s in srcs:
            if s.startswith(('http://', 'https://', 'data:')):
                continue
            p = (sheet.parent / s.split('?')[0].split('#')[0]).resolve()
            if p.exists():
                resolved.add(os.path.realpath(p))
        for sc in scenes:
            still = (ws / 'stills' / f'{sc["id"]}.svg').resolve()
            if os.path.realpath(still) not in resolved:
                fail(f'scene {sc["id"]} does not show its existing still stills/{sc["id"]}.svg '
                     f'(img srcs found: {srcs[:6]})')

    emit()


main()
