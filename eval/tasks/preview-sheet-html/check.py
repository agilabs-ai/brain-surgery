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

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
SPLIT = re.compile(r'[—–]|&mdash;|&#8212;|&#x2014;')


def fail(msg):
    print(msg)
    sys.exit(1)


def norm(s):
    return ' '.join(s.split())


def main():
    ws = Path(sys.argv[1])
    src = ws / 'scenes.json'
    if not src.exists():
        fail('scenes.json missing from the workspace')
    scenes = json.loads(src.read_text())['scenes']

    sheets = [p for p in ws.rglob('*.html') if p.is_file()]
    if not sheets:
        fail('no .html sheet was produced anywhere in the workspace')
    if len(sheets) > 1:
        names = sorted(str(p.relative_to(ws)) for p in sheets)
        fail(f'expected one sheet with all {len(scenes)} scenes, found {len(sheets)}: {names}')
    sheet = sheets[0]
    html = sheet.read_text(encoding='utf-8', errors='replace')
    flat = norm(html)

    m = DASH.search(html)
    if m:
        i = m.start()
        fail(f'em/en dash in {sheet.name} at offset {i}: ...{html[max(0, i - 45):i + 45]!r}')

    # Every scene present, in full.
    for sc in scenes:
        if sc['id'] not in html:
            fail(f'scene id {sc["id"]!r} is not in {sheet.name}')
        if norm(sc['title']) not in flat:
            fail(f'scene {sc["id"]} title {sc["title"]!r} is not in {sheet.name}')
        for frag in SPLIT.split(sc['voiceover']):
            frag = norm(frag).strip(' .,')
            if len(frag) < 12:
                continue
            if frag not in flat:
                fail(f'scene {sc["id"]} voiceover text is missing or was reworded: {frag!r}')

    # Every card shows the still that already exists, referenced by a resolving
    # relative path. Re-drawn placeholders and inline shapes do not count.
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

    print('ok')
    sys.exit(0)


main()
