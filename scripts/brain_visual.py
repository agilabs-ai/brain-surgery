"""Deterministic paired brain gauges for Brain Surgery by AGI Labs.
Each hemisphere's fill height encodes the measured test pass rate.
No image API, no decorative recoloring per user, no claim about theoretical AI potential.
"""
from __future__ import annotations
from pathlib import Path
import math
import re

ASSET = Path(__file__).resolve().parent.parent / 'assets' / 'brain.svg'


#: Literal palette, for a standalone file such as the social card, where a CSS
#: custom property has nothing to resolve against.
FIXED = {'ground': '#ffffff', 'current': '#050505', 'tested': '#154CFF',
         'quiet': '#b8b8b8', 'divide': '#e5e5e5', 'label': '#666666'}
#: Token palette, for an SVG inlined into a themed page. Same geometry, but the
#: colours follow the page rather than pinning it to a white ground, which is
#: what makes the gauge survive a dark viewer.
TOKENS = {'ground': 'var(--bg,#ffffff)', 'current': 'var(--ink,#050505)',
          'tested': 'var(--blue,#154CFF)', 'quiet': 'var(--brain-quiet,#b8b8b8)',
          'divide': 'var(--line,#e5e5e5)', 'label': 'var(--muted,#666666)'}


def brain_svg(before: float | None, after: float | None, prefix: str = 'brain',
              css_vars: bool = False,
              before_text: str = 'Current', after_text: str = 'Tested',
              show_labels: bool = True) -> str:
    """The two halves are captioned inside the drawing, so the caller has to be
    able to set those captions. Hard-coding "Current" and "Tested" let the SVG
    contradict the labels the page set beside it, which is the kind of mismatch
    a reader stops at.

    `show_labels=False` drops the drawn captions for a page that already sets
    them beside the halves, where drawing them again puts the same two words on
    screen twice. They stay in the aria-label either way, because a screen
    reader gets the figure without the page's own labels around it."""
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*', prefix):
        raise ValueError('Invalid SVG prefix')
    c = TOKENS if css_vars else FIXED
    for value in (before, after):
        if value is not None and (isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 100):
            raise ValueError('Percentages must be finite and within 0..100')

    text = ASSET.read_text(encoding='utf-8')
    group_match = re.search(r'<g transform=""[^>]*>(.*?)</g>', text)
    if not group_match:
        raise ValueError('Brain asset geometry unavailable')
    paths = re.findall(r'<path d="([^"]+)"', group_match.group(1))
    if len(paths) < 2:
        raise ValueError('Brain asset paths unavailable')
    outline, folds = paths[0], paths[1:]

    top, bottom = 44.0, 382.0
    span = bottom - top
    y_before = bottom if before is None else bottom - span * before / 100
    y_after = bottom if after is None else bottom - span * after / 100

    def hemi(transform: str, level: float, pct: float | None, suffix: str, active: str, quiet: str):
        fold_paths = ''.join(f'<path d="{d}"/>' for d in folds)
        height = bottom - level
        level_line = ''
        if pct is not None and 0 < pct < 100:
            level_line = f'<path d="M29 {level:.3f}H212" stroke="{active}" stroke-width="2"/>'
        return f'''<g transform="{transform}">
<defs>
  <clipPath id="{prefix}-{suffix}-shape"><path d="{outline}"/></clipPath>
  <clipPath id="{prefix}-{suffix}-level"><rect x="20" y="{level:.3f}" width="195" height="{height:.3f}"/></clipPath>
</defs>
<path d="{outline}" fill="{c['ground']}" stroke="{quiet}" stroke-width="2.5"/>
<g clip-path="url(#{prefix}-{suffix}-shape)">
  <rect class="brain-fill" data-percent="{'' if pct is None else f'{pct:.5f}'}" data-side="{suffix}" x="20" y="{level:.3f}" width="195" height="{height:.3f}" fill="{active}" opacity=".10"/>
  <g stroke="{quiet}" stroke-width="2.35" fill="none" stroke-linecap="round" stroke-linejoin="round">{fold_paths}</g>
  <g clip-path="url(#{prefix}-{suffix}-level)" stroke="{active}" stroke-width="3.1" fill="none" stroke-linecap="round" stroke-linejoin="round">{fold_paths}<path d="{outline}"/></g>
  {level_line}
</g>
<g clip-path="url(#{prefix}-{suffix}-level)"><path d="{outline}" fill="none" stroke="{active}" stroke-width="3"/></g>
</g>'''

    before_label = '·' if before is None else str(math.floor(before + .5)) + '%'
    after_label = '·' if after is None else str(math.floor(after + .5)) + '%'
    esc = lambda s: (str(s).replace('&', '&amp;').replace('<', '&lt;')
                     .replace('>', '&gt;').replace('"', '&quot;'))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 438" fill="none" role="img" aria-label="Test pass rate: {esc(before_text)} {before_label}, {esc(after_text)} {after_label}. Each half fills to its measured rate.">
{hemi('', y_before, before, 'current', c['current'], c['quiet'])}
{hemi('translate(440 0) scale(-1 1)', y_after, after, 'tested', c['tested'], c['quiet'])}
<path d="M220 48v332" stroke="{c['divide']}" stroke-width="1"/>
{f"""<g font-family="Inter,-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif" font-size="12" font-weight="600" text-anchor="middle">
  <text x="126" y="418" fill="{c['label']}">{esc(before_text)}</text>
  <text x="314" y="418" fill="{c['tested']}">{esc(after_text)}</text>
</g>""" if show_labels else ''}
</svg>'''
