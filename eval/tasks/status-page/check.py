#!/usr/bin/env python3
# provenance: shape `status-artifact`, seen in 10 sessions.
# Hard rules cited: HR-1 (no em dashes, in any encoding), plus the house status-page
#                   contract from the same shape (fragment skeleton, self-contained,
#                   theme-aware palette on bare :root).
"""Verifier for status-page.

Everything here is a parse of the produced HTML. No browser, no network.
"""
import re
import sys
from pathlib import Path

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
ITEM = re.compile(r'\bOI-1\d\d\b')
SKELETON = [('<!doctype', re.compile(r'<!doctype', re.I)),
            ('<html>', re.compile(r'<html[\s>]', re.I)),
            ('<head>', re.compile(r'<head[\s>]', re.I)),
            ('<body>', re.compile(r'<body[\s>]', re.I))]
RESOURCE = re.compile(
    r'<(img|script|link|iframe|source|audio|video)\b[^>]*?\s(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.I)
DECISION_IDS = ['OI-101', 'OI-104', 'OI-106']


def fail(msg):
    print(msg)
    sys.exit(1)


def strip_comments(css):
    return re.sub(r'/\*.*?\*/', ' ', css, flags=re.S)


def parse_css(css):
    """[(at_rule_context, selector, declarations)] preserving @media context."""
    out, stack, buf, i = [], [], '', 0
    n = len(css)
    while i < n:
        c = css[i]
        if c == '{':
            prelude = ' '.join(buf.split())
            buf = ''
            nxt_open = css.find('{', i + 1)
            nxt_close = css.find('}', i + 1)
            if nxt_close != -1 and (nxt_open == -1 or nxt_close < nxt_open):
                out.append((list(stack), prelude, css[i + 1:nxt_close]))
                i = nxt_close + 1
                continue
            stack.append(prelude)
        elif c == '}':
            if stack:
                stack.pop()
            buf = ''
        else:
            buf += c
        i += 1
    return out


def decls(body):
    d = {}
    for part in body.split(';'):
        if ':' not in part:
            continue
        k, _, v = part.partition(':')
        d[k.strip()] = v.strip()
    return d


def main():
    ws = Path(sys.argv[1])
    if not (ws / 'notes').is_dir():
        fail('notes/ missing from the workspace')

    pages = [p for p in sorted(ws.rglob('*.html')) if p.is_file()]
    if not pages:
        fail('no HTML status page was produced')
    if len(pages) > 1:
        fail(f'expected one page, found {len(pages)}: {sorted(str(p.relative_to(ws)) for p in pages)}')
    page = pages[0]
    html = page.read_text(encoding='utf-8', errors='replace')

    m = DASH.search(html)
    if m:
        i = m.start()
        fail(f'em/en dash at offset {i}: ...{html[max(0, i - 45):i + 45]!r}')

    for label, rx in SKELETON:
        mm = rx.search(html)
        if mm:
            fail(f'page emits its own {label} at offset {mm.start()}; a status page is a fragment')

    titles = re.findall(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    if len(titles) != 1 or not titles[0].strip():
        fail(f'expected exactly one non-empty <title>, found {len(titles)}')

    found = set(ITEM.findall(html))
    expected = set()
    for nf in sorted((ws / 'notes').glob('*.md')):
        expected |= set(ITEM.findall(nf.read_text(encoding='utf-8', errors='replace')))
    missing = sorted(expected - found)
    if missing:
        fail(f'open items missing from the page: {missing}')

    n_flag = len(re.findall(r'Needs:\s*you', html))
    if n_flag != len(DECISION_IDS):
        fail(f'expected exactly {len(DECISION_IDS)} rows marked "Needs: you" '
             f'(the owner: you items {DECISION_IDS}), found {n_flag}')

    for tag, ref in RESOURCE.findall(html):
        r = ref.strip()
        if r.startswith('#') or r.startswith('data:'):
            continue
        if re.match(r'https?://|//', r):
            fail(f'<{tag.lower()}> loads {r!r} from the network; the page has to be self-contained')
        if not (page.parent / r.split('?')[0].split('#')[0]).exists():
            fail(f'<{tag.lower()}> references {r!r} which does not exist on disk')

    css = ' '.join(strip_comments(s) for s in re.findall(r'<style[^>]*>(.*?)</style>', html, re.S | re.I))
    if not css.strip():
        fail('page has no <style> block, so it has no palette and no dark mode')
    for u in re.findall(r'url\(\s*["\']?([^"\')]+)', css):
        if re.match(r'https?://|//', u.strip()):
            fail(f'stylesheet loads {u.strip()!r} from the network; the page has to be self-contained')
    if re.search(r'@import', css, re.I):
        fail('stylesheet uses @import; the page has to be self-contained')

    rules = parse_css(css)
    root_vars, dark_vars, body_bg = {}, {}, False
    dark_block_seen = False
    for ctx, sel, body in rules:
        ctxs = ' '.join(ctx).lower()
        in_dark = 'prefers-color-scheme' in ctxs and 'dark' in ctxs
        if 'prefers-color-scheme' in ctxs and 'dark' in ctxs:
            dark_block_seen = True
        d = decls(body)
        if ':root' in sel or re.search(r'(^|[\s,])html([\s,{]|$)', sel):
            for k, v in d.items():
                if k.startswith('--'):
                    (dark_vars if in_dark else root_vars)[k] = v
        if re.search(r'(^|[\s,>])body([\s,:.\[]|$)', sel) and not in_dark:
            if 'background' in d or 'background-color' in d:
                body_bg = True

    if len(root_vars) < 3:
        fail(f'bare :root defines only {len(root_vars)} custom properties; '
             'the light palette has to live on bare :root')
    if not dark_block_seen:
        fail('no @media (prefers-color-scheme: dark) block; the page is not theme-aware')
    orphan = sorted(k for k in dark_vars if k not in root_vars)
    if orphan:
        fail(f'colour tokens defined only in the dark block, never on bare :root: {orphan}')
    if not body_bg:
        fail('body has no explicit background; the viewer paints its own ground behind a transparent page')

    print('ok')
    sys.exit(0)


main()
