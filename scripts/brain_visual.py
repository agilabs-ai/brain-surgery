"""Deterministic paired brain gauges for Brain Surgery by AGI Labs.
Each hemisphere's fill height encodes the measured test pass rate.
No image API, no decorative recoloring per user, no claim about theoretical AI potential.
"""
from __future__ import annotations
from pathlib import Path
import math
import re

ASSET = Path(__file__).resolve().parent.parent / 'assets' / 'brain.svg'


def brain_svg(before: float | None, after: float | None, prefix: str = 'brain') -> str:
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*', prefix):
        raise ValueError('Invalid SVG prefix')
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
<path d="{outline}" fill="#ffffff" stroke="{quiet}" stroke-width="2.5"/>
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
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 440 438" fill="none" role="img" aria-label="Test pass rate: current {before_label}, tested changes {after_label}. Each half fills to its measured rate.">
{hemi('', y_before, before, 'current', '#050505', '#b8b8b8')}
{hemi('translate(440 0) scale(-1 1)', y_after, after, 'tested', '#154CFF', '#b8b8b8')}
<path d="M220 48v332" stroke="#e5e5e5" stroke-width="1"/>
<g font-family="Inter,-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif" font-size="11" font-weight="600" letter-spacing="1.2" text-anchor="middle">
  <text x="126" y="418" fill="#666666">CURRENT</text>
  <text x="314" y="418" fill="#154CFF">TESTED</text>
</g>
</svg>'''
