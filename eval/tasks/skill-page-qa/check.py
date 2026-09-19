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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

MIN_DESC = 40
BANNED = [
    ('github.com', 'a source-repo link'),
    ('npx skills add', 'an install command'),
    ('apache 2.0', 'licence vocabulary'),
    ('apache-2.0', 'licence vocabulary'),
]
URL = re.compile(r'https?://[^\s"\'<>)\]]+')
ALLOWED_HOSTS = {'catalog.example', 'www.w3.org'}


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


ws = Path(sys.argv[1])
cf = ws / 'catalog.json'
pages_root = ws / 'dist' / 'pages'

# The catalog and the built pages are read once, outside the sections, because
# every section below needs them and each one guards on its own.
entries = None
catalog_error = None
if not cf.exists():
    catalog_error = 'catalog.json missing from the workspace'
else:
    try:
        cat = json.loads(cf.read_text())
    except json.JSONDecodeError as e:
        cat = None
        catalog_error = f'catalog.json no longer parses as JSON: {e}'
    if catalog_error is None:
        loaded = cat['skills'] if isinstance(cat, dict) else cat
        if not isinstance(loaded, list) or not loaded:
            catalog_error = 'catalog.json has no skill entries'
        else:
            entries = loaded

ids = [e['id'] for e in (entries or []) if isinstance(e, dict) and e.get('id')]
pages = {}
for sid in ids:
    page = pages_root / sid / 'index.html'
    pages[sid] = page.read_text(encoding='utf-8', errors='replace') if page.exists() else None

# 1. the source of truth still parses.
# Outcome: the prompt names catalog.json as the source of truth, so a QA pass
# that leaves it broken has destroyed the thing it was sent to check.
with section('catalog-parses', 'outcome'):
    if catalog_error:
        fail(catalog_error)

# 2. the publish bar's required fields.
# Convention: the required key set, 'evals' in particular, is nowhere in the
# prompt; only the skill says an entry is incomplete without it.
with section('catalog-entry-fields', 'convention'):
    if entries is None:
        fail('no catalog entries to check')
    for i, e in enumerate(entries):
        for k in ('id', 'title', 'description', 'logo', 'evals'):
            if k not in e or e[k] in (None, '', {}, []):
                fail(f'catalog entry {e.get("id", i)!r} is missing a usable {k!r}')

# 3. the minimum description length.
# Convention: 40 characters is a number that exists only in the skill; the prompt
# says "some of these look unprofessional" and names no threshold.
with section('description-length', 'convention'):
    if entries is None:
        fail('no catalog entries to check')
    for i, e in enumerate(entries):
        d = str(e.get('description', '')).strip()
        if len(d) < MIN_DESC:
            fail(f'{e.get("id", i)}: description is {len(d)} chars, the publish bar is {MIN_DESC}')

# 4. no placeholder copy shipped.
# Outcome: a description still reading TODO is exactly the "looks unprofessional
# next to the others" the prompt asks to be fixed.
with section('description-not-placeholder', 'outcome'):
    if entries is None:
        fail('no catalog entries to check')
    for i, e in enumerate(entries):
        d = str(e.get('description', '')).strip()
        if 'todo' in d.lower() or 'tbd' in d.lower():
            fail(f'{e.get("id", i)}: description is still a placeholder: {d!r}')

# 5. the logo resolves.
# Outcome: a catalog pointing at a file that is not on disk is a broken asset,
# which any careful QA pass catches without being told.
with section('logo-resolves', 'outcome'):
    if entries is None:
        fail('no catalog entries to check')
    for i, e in enumerate(entries):
        if not e.get('logo'):
            fail(f'catalog entry {e.get("id", i)!r} has no logo to resolve')
        if not (ws / e['logo']).exists():
            fail(f'{e.get("id", i)}: logo {e["logo"]!r} does not resolve to a file on disk')

# 6. the logo is a real mark.
# Outcome: a 40 byte stub where a logo should be is a visibly broken page, the
# unprofessional thing the prompt points at.
with section('logo-is-a-real-image', 'outcome'):
    if entries is None:
        fail('no catalog entries to check')
    for i, e in enumerate(entries):
        logo = ws / str(e.get('logo', ''))
        if not e.get('logo') or not logo.is_file():
            fail(f'{e.get("id", i)}: no logo file to inspect')
        ok, why = looks_like_image(logo)
        if not ok:
            fail(f'{e.get("id", i)}: {why}')

# 7. what is served matches what is listed.
# Outcome: the prompt states it itself, "catalog.json is the source of truth and
# dist/pages is what actually gets served"; a listed skill with no page is a 404.
with section('pages-match-catalog', 'outcome'):
    if entries is None:
        fail('no catalog entries to compare dist/pages against')
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

# 8. each page directory really serves a page.
# Outcome: a page directory with no index.html serves nothing, which is the same
# 404 the prompt's own framing rules out.
with section('page-index-present', 'outcome'):
    if not ids:
        fail('no catalog entries, so no pages to check')
    for sid in ids:
        if pages[sid] is None:
            fail(f'{sid}: dist/pages/{sid}/index.html is missing')

# 9. the social metadata block.
# Convention: the prompt asks for a QA pass and never mentions metadata; which
# tags a page must carry before it may publish is the skill's bar.
with section('page-social-metadata', 'convention'):
    if not ids:
        fail('no catalog entries, so no pages to check')
    for sid in ids:
        if pages[sid] is None:
            fail(f'{sid}: no page to read metadata from')
        low = pages[sid].lower()
        for tag in ('og:title', 'og:image', 'twitter:card'):
            if tag not in low:
                fail(f'{sid}: page has no {tag} metadata')

# 10. the banned vocabulary.
# Convention: HR-3. That a repo link, an install command or a licence name may
# not appear in audience-facing copy is a house rule, stated nowhere in the prompt.
with section('no-banned-vocabulary', 'convention'):
    if not ids:
        fail('no catalog entries, so no pages to check')
    for sid in ids:
        if pages[sid] is None:
            fail(f'{sid}: no page to read copy from')
        low = pages[sid].lower()
        for needle, what in BANNED:
            if needle in low:
                fail(f'{sid}: page still carries {what} ({needle!r})')

# 11. the canonical catalog link.
# Convention: HR-3 again; the exact https://catalog.example/skills/<id>/ target
# is knowable only from the skill.
with section('links-to-catalog-page', 'convention'):
    if not ids:
        fail('no catalog entries, so no pages to check')
    for sid in ids:
        if pages[sid] is None:
            fail(f'{sid}: no page to read links from')
        if not re.search(r'https://catalog\.example/skills/' + re.escape(sid) + r'/?', pages[sid]):
            fail(f'{sid}: page does not link to https://catalog.example/skills/{sid}/')

# 12. the off-site link allowlist.
# Convention: the allowed hosts are a local policy; the prompt never says a page
# may not link out.
with section('no-offsite-links', 'convention'):
    if not ids:
        fail('no catalog entries, so no pages to check')
    for sid in ids:
        if pages[sid] is None:
            fail(f'{sid}: no page to read links from')
        for u in URL.findall(pages[sid]):
            h = host_of(u)
            if h and h not in ALLOWED_HOSTS:
                fail(f'{sid}: page links off-site to {u!r}')

emit()
