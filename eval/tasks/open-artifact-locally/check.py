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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

HEADINGS = ['What landed', 'What is stuck', 'What we are asking for']
BODY_BITS = [
    'Brightmoor Foods',
    'Ridgeway',
    'cost centre',
]
RESOURCE = re.compile(
    r'<(img|script|link)\b[^>]*?\s(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.I)


def norm(s):
    return ' '.join(s.split())


def main():
    ws = Path(sys.argv[1])

    # Outcome: the brief is the input the prompt points at; consuming it is not a
    # licence to destroy it, and losing the only copy is the real failure mode.
    with section('source-brief-intact', 'outcome'):
        if not (ws / 'tmp' / 'draft-brief.md').exists():
            fail('tmp/draft-brief.md missing from the workspace')

    htmls = [p for p in sorted(ws.rglob('*.html')) if p.is_file()]
    in_scratch = [p for p in htmls if p.relative_to(ws).parts[0] == 'tmp']
    durable = [p for p in htmls if p.relative_to(ws).parts[0] == 'context']
    # The page is picked up wherever it landed, so a deliverable written to the
    # wrong directory still earns or loses its content checks on its own merits
    # instead of collapsing into the path convention.
    page = durable[0] if durable else (htmls[0] if htmls else None)
    html = page.read_text(encoding='utf-8', errors='replace') if page else ''

    # Outcome: "give me a single-page HTML version" is the request, in the
    # prompt, in those words.
    with section('single-html-page', 'outcome'):
        if not htmls:
            fail('no HTML file was produced anywhere in the workspace')
        if len(htmls) > 1:
            where = sorted(str(p.relative_to(ws)) for p in htmls)
            fail(f'expected one page, found {len(htmls)}: {where}')

    # Convention: HR-10. The prompt names tmp/ only as the source and never says
    # where the result goes, so "not in the scratch directory" is a house rule.
    with section('deliverable-not-in-scratch', 'convention'):
        if not htmls:
            fail('no HTML file was produced anywhere in the workspace')
        if in_scratch:
            where = sorted(str(p.relative_to(ws)) for p in in_scratch)
            fail(f'the deliverable was left in the scratch directory: {where}')

    # Convention: the exact durable directory name context/ appears nowhere in
    # the prompt or the seeded tree; it is knowable only from the skill.
    with section('deliverable-under-context', 'convention'):
        if not htmls:
            fail('no HTML file was produced anywhere in the workspace')
        if not durable:
            where = sorted(str(p.relative_to(ws)) for p in htmls)
            fail(f'no HTML under context/; the deliverable was written to {where} instead')

    # Outcome: an HTML version "of it" has to actually carry the brief; a page
    # that drops the readout is the wrong deliverable however it is filed.
    with section('page-carries-brief', 'outcome'):
        if page is None:
            fail('no HTML page was produced, so there is nothing carrying the brief')
        if len(html.strip()) < 800:
            fail(f'{page.name} is only {len(html.strip())} chars; the brief was not carried over')
        flat = norm(html)
        for h in HEADINGS + BODY_BITS:
            if norm(h) not in flat:
                fail(f'{page.name} does not carry {h!r} from the brief')

    # Outcome: the prompt asks for something to read in a browser, and a titled
    # document is basic HTML correctness any careful agent gets right.
    with section('page-has-title', 'outcome'):
        if page is None:
            fail('no HTML page was produced, so there is no <title> to check')
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
        if not m or not m.group(1).strip():
            fail(f'{page.name} has no non-empty <title>')

    refs = RESOURCE.findall(html)
    resolved = set()
    for _tag, ref in refs:
        r = ref.strip()
        if r.startswith('data:') or r.startswith('#') or re.match(r'https?://|//', r):
            continue
        p = (page.parent / r.split('?')[0].split('#')[0]).resolve() if page else None
        if p is not None and p.exists():
            resolved.add(os.path.realpath(p))

    # Outcome: a page whose own references do not resolve is broken on the
    # machine it was written on, which no careful agent ships.
    with section('page-refs-resolve', 'outcome'):
        if page is None:
            fail('no HTML page was produced, so no references could be resolved')
        for _tag, ref in refs:
            r = ref.strip()
            if r.startswith('data:') or r.startswith('#') or re.match(r'https?://|//', r):
                continue
            p = (page.parent / r.split('?')[0].split('#')[0]).resolve()
            if not p.exists():
                fail(f'{page.name} references {r!r} which does not resolve from {page.parent.name}/')

    # Convention: the prompt asks for a page to read in a browser and never says
    # it has to work offline, so standing alone is the house rule, not the ask.
    with section('page-no-network-refs', 'convention'):
        if page is None:
            fail('no HTML page was produced, so its references could not be checked')
        for tag, ref in refs:
            r = ref.strip()
            if re.match(r'https?://|//', r):
                fail(f'{page.name} pulls <{tag.lower()}> from the network: {r!r}; '
                     f'the page has to stand alone')

    # Convention: HR-13. The prompt never mentions assets/cover.svg at all, so
    # reusing that exact existing file rather than drawing one is skill-only.
    with section('shows-existing-cover', 'convention'):
        if page is None:
            fail('no HTML page was produced, so the existing cover cannot be shown')
        cover = os.path.realpath((ws / 'assets' / 'cover.svg').resolve())
        if cover not in resolved:
            shown = [r for _, r in refs][:6]
            fail(f'{page.name} does not show the existing assets/cover.svg (refs found: {shown})')

    emit()


main()
