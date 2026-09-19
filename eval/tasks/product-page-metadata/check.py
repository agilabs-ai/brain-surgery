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

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
META = re.compile(r'<meta\b[^>]*>', re.I)
ATTR = re.compile(r'(\w[\w:.-]*)\s*=\s*"([^"]*)"|(\w[\w:.-]*)\s*=\s*\'([^\']*)\'')
TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
SITE = 'https://toolshelf.example'


def fail(msg):
    print(msg)
    sys.exit(1)


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
if not cat_path.exists():
    fail('catalog.json missing')
cat = json.loads(cat_path.read_text(encoding='utf-8'))
tools = cat['tools'] if isinstance(cat, dict) else cat

pages_dir = ws / 'site' / 'pages'
if not pages_dir.is_dir():
    fail('site/pages/ missing')
on_disk = {p.stem for p in pages_dir.glob('*.html')}
in_catalog = {t['id'] for t in tools}
orphans = sorted(on_disk - in_catalog)
if orphans:
    fail(f'site/pages/ still holds pages with no catalog entry: {orphans}; the catalog '
         f'is the source of truth for which pages exist')
missing = sorted(in_catalog - on_disk)
if missing:
    fail(f'catalog entries with no page, so they 404: {missing}')

for tool in tools:
    tid = tool['id']
    page = ws / 'site' / 'pages' / f'{tid}.html'
    if not page.exists():
        fail(f'site/pages/{tid}.html missing')
    doc = page.read_text(encoding='utf-8', errors='replace')

    head = doc.split('</head>')[0] if '</head>' in doc else doc
    m = DASH.search(head)
    if m:
        s = max(0, m.start() - 40)
        fail(f'{tid}.html: em dash in page metadata: ...{head[s:m.end() + 40]!r}')

    tags = metas(doc)
    for key in ('og:title', 'og:description', 'og:image', 'og:url', 'twitter:card'):
        if key not in tags:
            fail(f'{tid}.html is missing {key}; tags present: {sorted(tags)}')

    if norm(tags['og:title']) != norm(tool['title']):
        fail(f'{tid}.html og:title is {tags["og:title"]!r}; it must be the catalog title '
             f'verbatim, {tool["title"]!r}')
    if norm(tags['og:description']) != norm(tool['description']):
        fail(f'{tid}.html og:description is {tags["og:description"]!r}; it must be the '
             f'catalog description verbatim')

    img = norm(tags['og:image'])
    expect_img = f'{SITE}/assets/og/{tid}.png'
    if img != expect_img:
        fail(f'{tid}.html og:image is {img!r}; it must be the absolute URL {expect_img!r}')
    asset = ws / 'site' / 'assets' / 'og' / f'{tid}.png'
    if not asset.exists():
        fail(f'og:image points at {img} but site/assets/og/{tid}.png does not exist')
    if asset.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
        fail(f'site/assets/og/{tid}.png is not a PNG any more')

    url = norm(tags['og:url'])
    expect_url = f'{SITE}/tools/{tid}/'
    if url != expect_url:
        fail(f'{tid}.html og:url is {url!r}; expected {expect_url!r}')

    if norm(tags['twitter:card']) != 'summary_large_image':
        fail(f'{tid}.html twitter:card is {tags["twitter:card"]!r}; expected '
             f'"summary_large_image"')

    t = TITLE.search(doc)
    if not t or not t.group(1).strip():
        fail(f'{tid}.html lost its <title>')

    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', doc, re.I | re.S)
    if not h1 or norm(h1.group(1)) != norm(tool['title']):
        fail(f'{tid}.html has no <h1> holding the catalog title {tool["title"]!r}')
    page_body = doc.split('</head>')[-1]
    if norm(tool['description']) not in norm(page_body):
        fail(f'{tid}.html body does not carry the catalog description as its lede')

print('ok')
sys.exit(0)
