#!/usr/bin/env python3
# provenance: shape `open-artifact-on-my-mac`, seen in 13 sessions.
# Hard rules cited: HR-10 (durable artifacts never live in a scratch/tmp directory),
#                   HR-13 (never regenerate an asset that already exists).
"""Verifier for open-artifact-locally.

The deliverable has to survive: a real, self-contained HTML file at a durable
path, showing the cover that already exists rather than a freshly drawn one.
"""
import os
import re
import sys
from pathlib import Path

HEADINGS = ['What landed', 'What is stuck', 'What we are asking for']
BODY_BITS = [
    'Brightmoor Foods',
    'Ridgeway',
    'cost centre',
]
RESOURCE = re.compile(
    r'<(img|script|link)\b[^>]*?\s(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.I)


def fail(msg):
    print(msg)
    sys.exit(1)


def norm(s):
    return ' '.join(s.split())


def main():
    ws = Path(sys.argv[1])
    if not (ws / 'tmp' / 'draft-brief.md').exists():
        fail('tmp/draft-brief.md missing from the workspace')

    htmls = [p for p in sorted(ws.rglob('*.html')) if p.is_file()]
    if not htmls:
        fail('no HTML file was produced anywhere in the workspace')

    in_scratch = [p for p in htmls if p.relative_to(ws).parts[0] == 'tmp']
    if in_scratch:
        where = sorted(str(p.relative_to(ws)) for p in in_scratch)
        fail(f'the deliverable was left in the scratch directory: {where}')

    durable = [p for p in htmls if p.relative_to(ws).parts[0] == 'context']
    if not durable:
        where = sorted(str(p.relative_to(ws)) for p in htmls)
        fail(f'no HTML under context/; the deliverable was written to {where} instead')
    if len(durable) > 1:
        where = sorted(str(p.relative_to(ws)) for p in durable)
        fail(f'expected one page, found {len(durable)}: {where}')

    page = durable[0]
    html = page.read_text(encoding='utf-8', errors='replace')
    if len(html.strip()) < 800:
        fail(f'{page.name} is only {len(html.strip())} chars; the brief was not carried over')

    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    if not m or not m.group(1).strip():
        fail(f'{page.name} has no non-empty <title>')

    flat = norm(html)
    for h in HEADINGS + BODY_BITS:
        if norm(h) not in flat:
            fail(f'{page.name} does not carry {h!r} from the brief')

    refs = RESOURCE.findall(html)
    resolved = set()
    for tag, ref in refs:
        r = ref.strip()
        if r.startswith('data:') or r.startswith('#'):
            continue
        if re.match(r'https?://|//', r):
            fail(f'{page.name} pulls <{tag.lower()}> from the network: {r!r}; the page has to stand alone')
        p = (page.parent / r.split('?')[0].split('#')[0]).resolve()
        if not p.exists():
            fail(f'{page.name} references {r!r} which does not resolve from {page.parent.name}/')
        resolved.add(os.path.realpath(p))

    cover = os.path.realpath((ws / 'assets' / 'cover.svg').resolve())
    if cover not in resolved:
        shown = [r for _, r in refs][:6]
        fail(f'{page.name} does not show the existing assets/cover.svg (refs found: {shown})')

    print('ok')
    sys.exit(0)


main()
