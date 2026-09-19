#!/usr/bin/env python3
# provenance: shape `getedge-skill-page-qa` (generic: catalog page QA), seen in 9 sessions.
# Hard rules cited: HR-3 (link the catalog page, never the source repo; no licence or
#                   install-command vocabulary in audience-facing copy).
"""Verifier for skill-page-qa.

Everything is checked against the local catalog fixture and the built page tree.
No network: the "404" assertion is a file-existence assertion.
"""
import json
import re
import sys
from pathlib import Path

MIN_DESC = 40
BANNED = [
    ('github.com', 'a source-repo link'),
    ('npx skills add', 'an install command'),
    ('apache 2.0', 'licence vocabulary'),
    ('apache-2.0', 'licence vocabulary'),
]
URL = re.compile(r'https?://[^\s"\'<>)\]]+')
ALLOWED_HOSTS = {'catalog.example', 'www.w3.org'}


def fail(msg):
    print(msg)
    sys.exit(1)


def host_of(u):
    m = re.match(r'https?://([^/]+)', u)
    return m.group(1).lower() if m else ''


def looks_like_image(p: Path):
    b = p.read_bytes()
    if len(b) < 120:
        return False, f'{p.name} is only {len(b)} bytes, that is a placeholder not a mark'
    head = b[:400].lstrip()
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return True, ''
    if b'<svg' in b[:2000] or head.startswith(b'<?xml'):
        if b'<svg' not in b:
            return False, f'{p.name} is xml but has no <svg> root'
        return True, ''
    return False, f'{p.name} is neither SVG nor PNG'


def main():
    ws = Path(sys.argv[1])
    cf = ws / 'catalog.json'
    if not cf.exists():
        fail('catalog.json missing from the workspace')
    try:
        cat = json.loads(cf.read_text())
    except json.JSONDecodeError as e:
        fail(f'catalog.json no longer parses as JSON: {e}')
    entries = cat['skills'] if isinstance(cat, dict) else cat
    if not isinstance(entries, list) or not entries:
        fail('catalog.json has no skill entries')

    ids = []
    for i, e in enumerate(entries):
        for k in ('id', 'title', 'description', 'logo', 'evals'):
            if k not in e or e[k] in (None, '', {}, []):
                fail(f'catalog entry {e.get("id", i)!r} is missing a usable {k!r}')
        sid = e['id']
        ids.append(sid)
        d = e['description'].strip()
        if len(d) < MIN_DESC:
            fail(f'{sid}: description is {len(d)} chars, the publish bar is {MIN_DESC}')
        if 'todo' in d.lower() or 'tbd' in d.lower():
            fail(f'{sid}: description is still a placeholder: {d!r}')
        logo = ws / e['logo']
        if not logo.exists():
            fail(f'{sid}: logo {e["logo"]!r} does not resolve to a file on disk')
        ok, why = looks_like_image(logo)
        if not ok:
            fail(f'{sid}: {why}')

    pages_root = ws / 'dist' / 'pages'
    if not pages_root.is_dir():
        fail('dist/pages is missing')
    built = sorted(p.name for p in pages_root.iterdir() if p.is_dir())
    if sorted(ids) != built:
        missing = sorted(set(ids) - set(built))
        orphan = sorted(set(built) - set(ids))
        bits = []
        if missing:
            bits.append(f'no page for {missing} (those are 404s)')
        if orphan:
            bits.append(f'pages with no catalog entry: {orphan}')
        fail('dist/pages does not match the catalog: ' + '; '.join(bits))

    for sid in ids:
        page = pages_root / sid / 'index.html'
        if not page.exists():
            fail(f'{sid}: dist/pages/{sid}/index.html is missing')
        html = page.read_text(encoding='utf-8', errors='replace')
        low = html.lower()
        for tag in ('og:title', 'og:image', 'twitter:card'):
            if tag not in low:
                fail(f'{sid}: page has no {tag} metadata')
        for needle, what in BANNED:
            if needle in low:
                fail(f'{sid}: page still carries {what} ({needle!r})')
        if not re.search(r'https://catalog\.example/skills/' + re.escape(sid) + r'/?', html):
            fail(f'{sid}: page does not link to https://catalog.example/skills/{sid}/')
        for u in URL.findall(html):
            h = host_of(u)
            if h and h not in ALLOWED_HOSTS:
                fail(f'{sid}: page links off-site to {u!r}')

    print('ok')
    sys.exit(0)


main()
