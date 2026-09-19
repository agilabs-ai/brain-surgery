#!/usr/bin/env python3
# provenance: shape `seo-og-metadata`, seen in 3 sessions (conservative count); the
# metadata assertions are the ones listed under shape `getedge-skill-page-qa` (9 sessions).
# Hard rules enforced: HR-1 (no em dashes, any encoding, including &mdash; inside
# attributes), plus the house metadata block: catalog text verbatim, absolute image URL.
"""Verifier for product-page-metadata."""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from checklib import fail, report as emit, section  # noqa: E402

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
META = re.compile(r'<meta\b[^>]*>', re.I)
ATTR = re.compile(r'(\w[\w:.-]*)\s*=\s*"([^"]*)"|(\w[\w:.-]*)\s*=\s*\'([^\']*)\'')
TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
SITE = 'https://toolshelf.example'


def metas(doc):
    out = {}
    for tag in META.findall(doc):
        attrs = {}
        for m in ATTR.finditer(tag):
            k = (m.group(1) or m.group(3)).lower()
            v = m.group(2) if m.group(2) is not None else m.group(4)
            attrs[k] = v
        key = attrs.get('property') or attrs.get('name')
        if key:
            out.setdefault(key.lower(), attrs.get('content', ''))
    return out


def norm(s):
    return ' '.join(html.unescape(s).split())


ws = Path(sys.argv[1])
cat_path = ws / 'catalog.json'
pages_dir = ws / 'site' / 'pages'

# The catalog and the built pages are read once, outside the sections, because
# every section below needs them and each one guards on its own.
tools = None
catalog_error = None
if not cat_path.exists():
    catalog_error = 'catalog.json missing'
else:
    try:
        cat = json.loads(cat_path.read_text(encoding='utf-8'))
        tools = cat['tools'] if isinstance(cat, dict) else cat
    except Exception as e:  # noqa: BLE001 - reported as a failed check below
        catalog_error = f'catalog.json no longer parses: {e}'

on_disk = {p.stem for p in pages_dir.glob('*.html')} if pages_dir.is_dir() else set()
in_catalog = {t['id'] for t in tools} if tools else set()
docs = {}
for tid in sorted(in_catalog):
    page = pages_dir / f'{tid}.html'
    docs[tid] = page.read_text(encoding='utf-8', errors='replace') if page.exists() else None
tags_by_id = {tid: metas(d) if d else {} for tid, d in docs.items()}

# 1. the inputs the prompt names are still there.
# Outcome: the prompt points at site/pages/ and catalog.json by name; losing
# either of them is losing the job.
with section('catalog-and-pages-present', 'outcome'):
    if catalog_error:
        fail(catalog_error)
    if not pages_dir.is_dir():
        fail('site/pages/ missing')

# 2. no catalog entry 404s.
# Outcome: the prompt asks for the link preview to be sorted out "across the
# whole catalog", and a catalog entry with no page cannot have one.
with section('every-catalog-entry-has-a-page', 'outcome'):
    if tools is None:
        fail('no catalog to compare site/pages/ against')
    missing = sorted(in_catalog - on_disk)
    if missing:
        fail(f'catalog entries with no page, so they 404: {missing}')

# 3. no page outside the catalog.
# Convention: the prompt never asks for anything to be removed; "the catalog is
# the source of truth for which pages exist" is a house rule.
with section('no-orphan-pages', 'convention'):
    if tools is None:
        fail('no catalog to compare site/pages/ against')
    orphans = sorted(on_disk - in_catalog)
    if orphans:
        fail(f'site/pages/ still holds pages with no catalog entry: {orphans}; the catalog '
             f'is the source of truth for which pages exist')

# 4. the preview card tags exist at all.
# Outcome: "it came through as a bare URL, no preview card at all" is the
# complaint in the prompt; these five tags are what a preview card is made of.
with section('preview-tags-present', 'outcome'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        if docs.get(tid) is None:
            fail(f'site/pages/{tid}.html missing')
        for key in ('og:title', 'og:description', 'og:image', 'og:url', 'twitter:card'):
            if key not in tags_by_id[tid]:
                fail(f'{tid}.html is missing {key}; tags present: {sorted(tags_by_id[tid])}')

# 5. the card text.
# Convention: the prompt points at the catalog but never says the card text has
# to be the catalog title and description verbatim; that exactness is the skill's.
with section('preview-text-from-catalog', 'convention'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        tags = tags_by_id[tid]
        if docs.get(tid) is None:
            fail(f'site/pages/{tid}.html missing, so it carries no card text')
        if 'og:title' not in tags or 'og:description' not in tags:
            fail(f'{tid}.html has no og:title/og:description to compare with the catalog')
        if norm(tags['og:title']) != norm(tool['title']):
            fail(f'{tid}.html og:title is {tags["og:title"]!r}; it must be the catalog title '
                 f'verbatim, {tool["title"]!r}')
        if norm(tags['og:description']) != norm(tool['description']):
            fail(f'{tid}.html og:description is {tags["og:description"]!r}; it must be the '
                 f'catalog description verbatim')

# 6. the card image URL.
# Outcome: a preview card will not render a relative image, and catalog.json
# states the site origin, so the absolute URL is derivable from the workspace.
with section('og-image-absolute-url', 'outcome'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        tags = tags_by_id[tid]
        if 'og:image' not in tags:
            fail(f'{tid}.html has no og:image')
        img = norm(tags['og:image'])
        expect_img = f'{SITE}/assets/og/{tid}.png'
        if img != expect_img:
            fail(f'{tid}.html og:image is {img!r}; it must be the absolute URL {expect_img!r}')

# 7. the image the card points at is really there.
# Outcome: pointing a card at a missing or corrupted image is the same bare link
# the prompt complained about; no house rule is needed to want the asset intact.
with section('og-image-asset-intact', 'outcome'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        asset = ws / 'site' / 'assets' / 'og' / f'{tid}.png'
        if not asset.exists():
            img = norm(tags_by_id[tid].get('og:image', ''))
            fail(f'og:image points at {img} but site/assets/og/{tid}.png does not exist')
        if asset.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
            fail(f'site/assets/og/{tid}.png is not a PNG any more')

# 8. the canonical page URL on the card.
# Outcome: catalog.json carries pagePattern https://toolshelf.example/tools/<id>/,
# so the expected og:url is readable off the file the prompt names.
with section('og-url-canonical', 'outcome'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        tags = tags_by_id[tid]
        if 'og:url' not in tags:
            fail(f'{tid}.html has no og:url')
        url = norm(tags['og:url'])
        expect_url = f'{SITE}/tools/{tid}/'
        if url != expect_url:
            fail(f'{tid}.html og:url is {url!r}; expected {expect_url!r}')

# 9. the card size.
# Convention: any twitter:card value yields a card; "summary_large_image" is the
# house choice and the prompt names no value at all.
with section('twitter-card-type', 'convention'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        tags = tags_by_id[tid]
        if 'twitter:card' not in tags:
            fail(f'{tid}.html has no twitter:card')
        if norm(tags['twitter:card']) != 'summary_large_image':
            fail(f'{tid}.html twitter:card is {tags["twitter:card"]!r}; expected '
                 f'"summary_large_image"')

# 10. punctuation in the head.
# Convention: HR-1. The prompt asks for a preview card, never for a dash rule.
with section('no-em-dash-in-metadata', 'convention'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        doc = docs.get(tid)
        if doc is None:
            fail(f'site/pages/{tid}.html missing, so its metadata cannot be read')
        head = doc.split('</head>')[0] if '</head>' in doc else doc
        m = DASH.search(head)
        if m:
            s = max(0, m.start() - 40)
            fail(f'{tid}.html: em dash in page metadata: ...{head[s:m.end() + 40]!r}')

# 11. the page still has a title.
# Outcome: editing the head is the job, and stripping the <title> while doing it
# breaks the page for every reader, card or no card.
with section('page-title-kept', 'outcome'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        doc = docs.get(tid)
        if doc is None:
            fail(f'site/pages/{tid}.html missing, so it has no <title>')
        t = TITLE.search(doc)
        if not t or not t.group(1).strip():
            fail(f'{tid}.html lost its <title>')

# 12. the visible page carries the catalog copy.
# Convention: the prompt is about the link preview; that the <h1> and the lede
# must also be the catalog text is the house rule behind the preview block.
with section('page-body-matches-catalog', 'convention'):
    if tools is None:
        fail('no catalog to walk')
    for tool in tools:
        tid = tool['id']
        doc = docs.get(tid)
        if doc is None:
            fail(f'site/pages/{tid}.html missing, so it carries no catalog copy')
        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', doc, re.I | re.S)
        if not h1 or norm(h1.group(1)) != norm(tool['title']):
            fail(f'{tid}.html has no <h1> holding the catalog title {tool["title"]!r}')
        page_body = doc.split('</head>')[-1]
        if norm(tool['description']) not in norm(page_body):
            fail(f'{tid}.html body does not carry the catalog description as its lede')

emit()
