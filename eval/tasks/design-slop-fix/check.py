#!/usr/bin/env python3
# provenance: shape `design-slop-check`, seen in 11 sessions.
# Hard rules cited: HR-7 (banned mono ALL-CAPS wide-tracked micro-labels), HR-1 (no em dashes, any encoding).
"""Verifier for design-slop-fix.

Parses the CSS out of page.html and asserts the house visual rules. Pure
standard library, no browser, no network.
"""
import re
import sys
from pathlib import Path

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)

# Words that must survive the restyle, in their original casing. Hand-uppercasing
# a label instead of restyling it therefore fails here rather than sliding past.
KEEP = [
    'Tideline Freight',
    'Forty-one carriers',
    'Booked in ninety seconds',
    'One ledger',
    'Contracted carriers',
    'Capacity refresh',
    'Average rate delta',
    'board.svg',
]

CODEISH = re.compile(r'\b(code|pre|kbd|samp|tt)\b')


def fail(msg):
    print(msg)
    sys.exit(1)


def strip_comments(css):
    return re.sub(r'/\*.*?\*/', ' ', css, flags=re.S)


def declaration_blocks(css):
    """Return [(selector_text, declarations)] for every innermost block.

    Innermost blocks contain no braces, so matching and removing them
    repeatedly unwraps @media and friends without needing a real parser.
    """
    out = []
    work = css
    pat = re.compile(r'([^{}]*)\{([^{}]*)\}', re.S)
    while True:
        m = pat.search(work)
        if not m:
            break
        sel = ' '.join(m.group(1).split())
        body = m.group(2)
        if sel and not sel.startswith('@'):
            out.append((sel, body))
        work = work[:m.start()] + work[m.end():]
    return out


def decls(body):
    d = {}
    for part in body.split(';'):
        if ':' not in part:
            continue
        k, _, v = part.partition(':')
        d[k.strip().lower()] = v.strip().lower()
    return d


def length_em(value, default_font_px):
    """Return a letter-spacing value expressed in em, or None if not comparable."""
    v = value.strip()
    if v in ('normal', '', 'inherit', 'initial', 'unset'):
        return 0.0
    m = re.fullmatch(r'(-?[\d.]+)(em|rem|px|%)?', v)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2) or ('' if num == 0 else None)
    if unit in ('em', 'rem'):
        return num
    if unit == '%':
        return num / 100.0
    if unit == 'px':
        return num / float(default_font_px)
    if unit == '':
        return 0.0
    return None


def font_px(d):
    v = d.get('font-size')
    if not v:
        return None
    m = re.fullmatch(r'([\d.]+)(px|rem|em|pt)?', v.strip())
    if not m:
        return None
    n = float(m.group(1))
    u = m.group(2) or 'px'
    return {'px': n, 'pt': n * 1.333, 'rem': n * 16, 'em': n * 16}[u]


def main():
    ws = Path(sys.argv[1])
    f = ws / 'page.html'
    if not f.exists():
        fail('page.html missing')
    html = f.read_text(encoding='utf-8', errors='replace')
    if len(html.strip()) < 400:
        fail(f'page.html is only {len(html.strip())} chars; the page was gutted rather than restyled')

    for s in KEEP:
        if s not in html:
            fail(f'content was dropped or re-cased: {s!r} is no longer in page.html')

    m = DASH.search(html)
    if m:
        i = m.start()
        fail(f'em/en dash at offset {i}: ...{html[max(0, i - 40):i + 40]!r}')

    css = ' '.join(strip_comments(s) for s in re.findall(r'<style[^>]*>(.*?)</style>', html, re.S | re.I))
    if 'font-family' not in css:
        fail('no font-family left in page.html; the stylesheet was deleted instead of fixed')
    blocks = declaration_blocks(css)
    if len(blocks) < 8:
        fail(f'only {len(blocks)} CSS rules left; the stylesheet was deleted instead of fixed')

    for sel, body in blocks:
        d = decls(body)

        if d.get('text-transform') == 'uppercase':
            fail(f'text-transform: uppercase on selector {sel!r}')

        fam = d.get('font-family', '')
        if 'mono' in fam:
            parts = [p.strip() for p in sel.split(',') if p.strip()]
            offenders = [p for p in parts if not CODEISH.search(p)]
            if offenders:
                fail(f'monospace font-family on non-code selector {offenders[0]!r}: {fam!r}')

        if 'letter-spacing' in d:
            size = font_px(d)
            ls = length_em(d['letter-spacing'], size or 16)
            if ls is None:
                fail(f'unparseable letter-spacing {d["letter-spacing"]!r} on {sel!r}')
            if ls > 0.02 and (size is None or size < 24):
                shown = f'{size:.0f}px' if size else 'unset'
                fail(f'letter-spacing {d["letter-spacing"]!r} (> 0.02em) on {sel!r} at font-size {shown}')

    for m2 in re.finditer(r'style\s*=\s*"([^"]*)"', html, re.I):
        d = decls(m2.group(1))
        if d.get('text-transform') == 'uppercase':
            fail(f'inline text-transform: uppercase in style attribute {m2.group(1)!r}')
        if 'letter-spacing' in d:
            ls = length_em(d['letter-spacing'], font_px(d) or 16)
            if ls is not None and ls > 0.02 and (font_px(d) or 0) < 24:
                fail(f'inline letter-spacing {d["letter-spacing"]!r} (> 0.02em) in style attribute')
        if 'mono' in d.get('font-family', ''):
            fail(f'inline monospace font-family in style attribute {m2.group(1)!r}')

    print('ok')
    sys.exit(0)


main()
