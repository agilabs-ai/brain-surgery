#!/usr/bin/env python3
"""Render a brain-surgery/0.5 grid result as a single self-contained report.

This renderer consumes the 2x2 grid produced by `eval/to_result.py`, not the
older paired-task schema. The difference matters: the old schema could only say
"the candidate did better", while the grid can say what the candidate was worth
*compared to buying a better model*, which is the only version of the claim a
reader can act on.

Page order is an argument, not a layout:

  1. the brain, current versus tested, because that is the question asked
  2. the arms, so the reader sees all four conditions on one scale
  3. the 2x2, so the interaction between model and setup is visible
  4. the tasks, so the reader can count the sample themselves
  5. the method, where the sample is small enough to say so out loud

Renderer only. No evaluation, no upload, no live configuration edits. Standard
library only, and every asset is inlined so the file works over file://.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain_visual import brain_svg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'

# The contrast the hero asks about: the user's own setup, held against itself on
# one model. Everything else on the page is context for this number.
HERO_CONTRAST = 'setup_lift'

MARK = ('<svg class="mark" viewBox="0 0 100 66.6667" aria-hidden="true">'
        '<path d="M 0 50 A 50 50 0 0 1 100 50 L 100 66.6667 L 0 66.6667 Z" fill="currentColor"/></svg>')


def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def asset(name: str) -> str:
    """Inline an asset, or nothing. A missing chart file must not take the page down."""
    p = ASSETS / name
    return p.read_text(encoding='utf-8') if p.exists() else ''


def pct(v: float | None) -> str:
    return '&middot;' if v is None else f'{math.floor(v + 0.5)}'


def signed(v: float | None, places: int = 1) -> str:
    if v is None:
        return 'not measured'
    return f'{v:+.{places}f}'.rstrip('0').rstrip('.') if places else f'{v:+.0f}'


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate(raw: dict[str, Any]) -> dict[str, Any]:
    """Reject rather than coerce.

    A result that half-parses renders a page whose numbers came from somewhere
    the reader cannot see. Every failure below is a refusal to publish.
    """
    if raw.get('schema_version') != 'brain-surgery/0.5':
        raise ValueError('Unsupported schema_version: this renderer reads brain-surgery/0.5')
    if raw.get('metric_kind') != 'task_macro_pass_rate':
        raise ValueError('Only task_macro_pass_rate is implemented. Do not coerce ratings into pass rates.')

    grid = raw.get('grid')
    if not isinstance(grid, dict):
        raise ValueError('result needs a grid block')
    arms = grid.get('arms')
    if not isinstance(arms, dict) or not arms:
        raise ValueError('grid.arms must be a non-empty object')
    for k, arm in arms.items():
        if k not in ('A', 'B', 'C', 'D'):
            raise ValueError(f'unknown arm {k!r}')
        if not isinstance(arm.get('rate'), (int, float)) or not 0 <= arm['rate'] <= 100:
            raise ValueError(f'arm {k} needs a rate from 0 to 100')

    contrasts = raw.get('contrasts')
    if not isinstance(contrasts, dict) or not contrasts:
        raise ValueError('result needs at least one contrast')
    for name, c in contrasts.items():
        for side in ('before', 'after'):
            s = c.get(side)
            if not isinstance(s, dict) or not isinstance(s.get('rate'), (int, float)):
                raise ValueError(f'contrast {name}.{side} needs a rate')
            if not isinstance(s.get('passed'), int) or not isinstance(s.get('trials'), int):
                raise ValueError(f'contrast {name}.{side} needs integer passed/trials')
            if not 0 <= s['passed'] <= s['trials'] or s['trials'] < 1:
                raise ValueError(f'contrast {name}.{side} needs 0 <= passed <= trials')
        for key in ('improved_tasks', 'unchanged_tasks', 'regressed_tasks', 'tasks_compared'):
            if not isinstance(c.get(key), int) or c[key] < 0:
                raise ValueError(f'contrast {name} needs a non-negative integer {key}')
    if HERO_CONTRAST not in contrasts:
        raise ValueError(f'result is missing the {HERO_CONTRAST} contrast, which the page is built around')
    # A count that is not a count has no business being set in 14px type beside
    # three real counts. Anything else is refused rather than stringified.
    si = raw.get('skills_inspected', 0)
    if not isinstance(si, int) or isinstance(si, bool) or si < 0:
        raise ValueError('skills_inspected must be a non-negative integer')
    return raw


# --------------------------------------------------------------------------
# copy
# --------------------------------------------------------------------------

def headline(raw: dict[str, Any]) -> tuple[str, str]:
    """State the result, then the two quantities that make it a result.

    The strongest true sentence available, and no stronger. Where the sample
    cannot support a directional claim, the headline says what was measured
    instead of dressing noise as a finding.
    """
    cs = raw['contrasts']
    hero = cs[HERO_CONTRAST]
    setup = hero['delta_points']
    before, after = hero['before'], hero['after']

    # The headline has to be the claim the hero figure actually supports. The
    # brain draws one model with the skills off and the same model with them on,
    # so a headline about beating a model upgrade would be pointing at a bar that
    # is not there. That comparison is real and it gets its own block lower down.
    sub = (f'{after["passed"]} of {after["trials"]} trials passed with the skill in reach, '
           f'against {before["passed"]} of {before["trials"]} without them. '
           f'{hero["tasks_compared"]} tasks, same model on both sides, same checks. '
           f'Each task turns on a house convention the prompt never states, so this is '
           f'a measure of convention compliance and not of general ability.')

    if setup > 0:
        return (f'The skills took the same model from {pct(before["rate"])}% '
                f'to {pct(after["rate"])}%.', sub)
    if setup == 0:
        return ('Reaching the skills changed nothing.', sub)
    return (f'The same model scored {signed(setup)} points with the skills reachable.', sub)


def fmt_p(p: float | None) -> str:
    """A p-value rounded to 0 prints as `p = 0`, which is a claim no test makes.

    The exact test bottoms out at the smallest value the sample can produce, so
    below the display threshold it is reported as an inequality.
    """
    if p is None:
        return 'p not computed'
    if p < 0.001:
        return 'p < 0.001'
    if p >= 0.999:
        return 'p > 0.99'
    return f'p = {p:.3g}'


def verdict_line(raw: dict[str, Any]) -> str:
    """What the reader should do, and what happens if they do nothing.

    A report that stops at a number leaves the decision to the reader and calls
    that neutrality. The panel reading this page marked it down for exactly that,
    so the recommendation is stated, with the cost of ignoring it attached.
    """
    c = raw['contrasts'][HERO_CONTRAST]
    pairs = c.get('pairs') or []
    lost = sum(1 for p in pairs if not p.get('before') and p.get('after'))
    total = c['tasks_compared']
    if c['delta_points'] <= 0 or not lost:
        return ('Keep the setup under review. On these tasks it did not earn its place, '
                'and the honest read is that nothing here justifies the maintenance.')
    return (f'Keep the setup. Take it away and {lost} of {total} of these tasks stop passing '
            f'their checks, on the same model, with the same prompts.')


def strength_line(c: dict[str, Any]) -> str:
    """One sentence on what this sample can and cannot carry."""
    n = c['improved_tasks'] + c['regressed_tasks']
    p = c.get('mcnemar_p')
    if n == 0:
        return 'No task changed direction, so this sample shows no effect in either direction.'
    if p is not None and p > 0.05:
        return (f'{c["improved_tasks"]} tasks improved and {c["regressed_tasks"]} regressed. '
                f'At this sample size that is a direction, not proof (exact McNemar {fmt_p(p)}).')
    return (f'{c["improved_tasks"]} tasks improved and {c["regressed_tasks"]} regressed '
            f'(exact McNemar {fmt_p(p)}).')


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def hero_section(raw: dict[str, Any]) -> str:
    """The brain is the chart, not the ornament.

    Each hemisphere fills to its measured pass rate, current on the left and
    tested on the right, with the number it encodes set beside it. It is the
    top of the page because it answers the question the reader arrived with,
    and everything below it is the working.
    """
    c = raw['contrasts'][HERO_CONTRAST]
    before, after = c['before'], c['after']
    # css_vars so the gauge takes its colours from the page: the same file has
    # to hold up on a white ground and on a dark one.
    art = brain_svg(before['rate'], after['rate'], prefix='hero-brain', css_vars=True,
                    before_text='Skills off', after_text='Skills on')
    grid = raw['grid']
    return f'''<section class="hero" aria-labelledby="hero-title">
  <div class="hero-cloud" data-cloud></div>
  <div class="hero-copy">
    <p class="hero-kicker">{grid['tasks']} tasks taken from real sessions, each paired with the one installed skill that covers it, run with that skill out of reach and then in reach on the same model</p>
    <h1 id="hero-title">{esc(headline(raw)[0])}</h1>
    <p class="hero-sub">{esc(headline(raw)[1])}</p>
    <p class="hero-verdict">{esc(verdict_line(raw))}</p>
  </div>
  <figure class="hero-chart">
    <div class="hemi hemi-before">
      <div class="hemi-num">{pct(before['rate'])}<small>%</small></div>
      <div class="hemi-label">Skills off</div>
      <div class="hemi-count">{before['passed']}/{before['trials']} trials</div>
    </div>
    <div class="hero-brain">{art}</div>
    <div class="hemi hemi-after">
      <div class="hemi-num">{pct(after['rate'])}<small>%</small></div>
      <div class="hemi-label">Skills on</div>
      <div class="hemi-count">{after['passed']}/{after['trials']} trials</div>
    </div>
    <figcaption>Each half fills to its measured pass rate. {esc(strength_line(c))}</figcaption>
  </figure>
  <div class="hero-meta">
    <span><b>{grid['tasks']}</b> tasks</span>
    <span><b>{grid['trials_per_task']}</b> trials each</span>
    <span><b>{len(grid['arms'])}</b> conditions</span>
    <span><b>{raw.get('skills_inspected', 0)}</b> skills inspected</span>
  </div>
</section>'''


def chart_section(id_: str, kicker: str, title: str, lede: str, mount: str) -> str:
    return f'''<section class="chart-block" aria-labelledby="{id_}-title">
  <header class="block-head">
    <p class="kicker">{esc(kicker)}</p>
    <h2 id="{id_}-title">{esc(title)}</h2>
    <p class="lede">{esc(lede)}</p>
  </header>
  <div class="chart-mount" data-chart="{mount}"></div>
</section>'''


def cross_callout(raw: dict[str, Any]) -> str:
    """The cross-corner comparison, stated as a sentence with both numbers in it.

    This is the one finding a reader repeats to someone else, so it gets its own
    block rather than being left for them to compute off a bar chart.
    """
    c = raw['contrasts'].get('skill_vs_model')
    if not c:
        return ''
    weak, strong = c['after'], c['before']  # after = base+skill, before = strong alone
    verdict = ('beat' if c['delta_points'] > 0 else
               'matched' if c['delta_points'] == 0 else 'lost to')
    return f'''<section class="callout" aria-labelledby="cross-title">
  <p class="kicker">The cross comparison</p>
  <h2 id="cross-title">The cheaper model with the skill {esc(verdict)} the better model without it.</h2>
  <div class="callout-pair">
    <div><span class="callout-num">{pct(weak['rate'])}<small>%</small></span>
         <span class="callout-label">{esc(weak['label'])}</span></div>
    <div class="callout-vs" aria-hidden="true">vs</div>
    <div><span class="callout-num quiet">{pct(strong['rate'])}<small>%</small></span>
         <span class="callout-label">{esc(strong['label'])}</span></div>
  </div>
  <p class="callout-note">{esc(strength_line(c))} This holds on tasks that turn on a stated
  house convention. It is not a claim that the smaller model is the better model, and a reader
  who takes it that way has been misled by this page rather than by the data.</p>
</section>'''


def method_section(raw: dict[str, Any]) -> str:
    grid = raw['grid']
    hero = raw['contrasts'][HERO_CONTRAST]
    improved = hero['improved_tasks']
    trial_improved = hero.get('trial_level_improved', improved)
    rows = []
    for name, c in raw['contrasts'].items():
        g = c.get('normalized_gain')
        p_val = c.get('mcnemar_p')
        gain_cell = 'not defined' if g is None else f'{g:.1f}%'
        # None is "this contrast has no discordant tasks", which is a different
        # statement from a p of 1, and the table has to keep them apart.
        p_cell = 'not defined' if p_val is None else fmt_p(p_val).replace('p = ', '').replace('p ', '')
        delta = c['delta_points']
        tone = 'up' if delta > 0 else 'down' if delta < 0 else ''
        rows.append(
            f'<tr><td>{esc(c["label"])}</td>'
            f'<td class="num">{c["before"]["rate"]:.1f}</td>'
            f'<td class="num">{c["after"]["rate"]:.1f}</td>'
            f'<td class="num {tone}">{signed(delta)}</td>'
            f'<td class="num">{gain_cell}</td>'
            f'<td class="num">{c["improved_tasks"]}/{c["unchanged_tasks"]}/{c["regressed_tasks"]}</td>'
            f'<td class="num">{p_cell}</td></tr>')
    caveats = ''.join(f'<li>{esc(x)}</li>' for x in raw.get('caveats', []))
    excluded = raw.get('excluded') or []
    excl = (f'<p>{len(excluded)} runs were excluded as infrastructure failures, not as task failures. '
            f'A run that crashed or ran out of wall clock tells you nothing about the setup, and counting '
            f'it as a fail would flatter whichever condition happened to crash less.</p>'
            if excluded else
            '<p>No runs were excluded. Every run that started, finished and was scored.</p>')
    return f'''<section class="method" aria-labelledby="method-title">
  <header class="block-head">
    <p class="kicker">Method</p>
    <h2 id="method-title">Every number on this page, and how far it goes.</h2>
  </header>
  <div class="method-grid">
    <div class="method-text">
      <p><b>The metric.</b> Task-macro pass rate. Each task scores its own passes over trials,
      and the condition scores the mean of those. Pooling every trial instead would quietly hand
      more weight to whichever task happened to get more runs.</p>
      <p><b>Gain (g).</b> The share of the remaining headroom closed, delta divided by
      100 minus the starting rate. A move from 80 to 90 closes half the gap; a move from
      20 to 30 closes an eighth. Both are ten points, and they are not the same achievement.</p>
      <p><b>Two counts, deliberately.</b> The rate above is the mean of each task's pass
      fraction, so a task that goes from 0 of 3 to 1 of 3 moves it. The paired test needs a
      verdict rather than a fraction, so a task counts as passed when it passes more than half
      its trials, and only a task that flips from failing to passing counts as changed. That is
      why {trial_improved} tasks gained ground while {improved} of them actually flipped.</p>
      <p><b>The p value.</b> Exact McNemar on the tasks that flipped. Tasks that
      landed the same way in both conditions carry no information about the effect, so they
      are not counted. With fewer than five discordant tasks, the smallest two-sided p this
      design can produce is above 0.05, which means no sample this size can reach significance
      whatever it shows.</p>
      <p><b>Isolation.</b> Each run gets a fresh workspace and a config directory holding
      nothing but credentials, so the host machine's own installed skills, settings and memory
      are invisible to it. The one skill under test is then added back for the with-skill
      conditions only. The verifier is a fixed script that reads the finished workspace and
      never learns which condition produced it.</p>
      {excl}
    </div>
    <div class="method-side">
      <h3>What this does not show</h3>
      <ul class="caveats">{caveats}</ul>
      <dl class="spec">
        <dt>Base model</dt><dd>{esc(grid['models'].get('base', 'not recorded'))}</dd>
        <dt>Stronger model</dt><dd>{esc(grid['models'].get('strong', 'not recorded'))}</dd>
        <dt>Tasks</dt><dd>{grid['tasks']}</dd>
        <dt>Trials per task</dt><dd>{grid['trials_per_task']}</dd>
        <dt>Total runs</dt><dd>{grid['tasks'] * grid['trials_per_task'] * len(grid['arms'])}</dd>
        <dt>Verifier</dt><dd>{esc(raw.get('evaluator_type', 'not recorded'))}</dd>
      </dl>
    </div>
  </div>
  <div class="table-scroll">
  <table class="contrast-table">
    <caption>Every contrast in the grid, including the ones that did not go our way.</caption>
    <thead><tr><th>Contrast</th><th class="num">Before</th><th class="num">After</th>
    <th class="num">Delta</th><th class="num">Gain (g)</th>
    <th class="num" title="improved / unchanged / regressed tasks">i / u / r</th>
    <th class="num">p</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  </div>
</section>'''


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

def report_html(raw: dict[str, Any]) -> str:
    h1, _ = headline(raw)
    demo = bool(raw.get('example'))
    badge = ('<div class="demo-banner">Design preview. Illustrative results. '
             'Nothing was audited or uploaded.</div>' if demo else '')
    payload = json.dumps(raw, ensure_ascii=False, separators=(',', ':')) \
        .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<meta name="referrer" content="no-referrer">
<title>Brain Surgery report</title>
<meta name="description" content="{esc(h1)} Measured across four conditions on one machine's real work.">
<style>{asset('grid-report.css')}</style>
<style>{asset('charts.css')}</style>
<style>{asset('cloud.css')}</style>
</head><body>
{badge}
<div class="wrap">
<nav class="nav" aria-label="Report header">
  <span class="brand">{MARK}agi labs</span>
  <span class="nav-note">Brain Surgery &middot; local result, not shared</span>
</nav>
<main>
{hero_section(raw)}
{chart_section('arms', 'All four conditions',
               'Two models, with and without the skill.',
               'One bar per model. The solid part is the rate without the skill, the pale part is '
               'what the skill added, and the grey tail is what neither reached.',
               'arms')}
{cross_callout(raw)}
{chart_section('grid', 'The interaction',
               'What each change was worth on its own.',
               'Moving across adds the skill. Moving down upgrades the model. The two do not '
               'behave the same way, which is the finding.',
               'interaction')}
{chart_section('tasks', 'The sample, in full',
               'Every task, every trial, every condition.',
               'Small samples are easy to over-read, so the whole thing is here to be counted '
               'rather than summarised away.',
               'taskGrid')}
{method_section(raw)}
</main>
<footer class="footer">
  <span>Brain Surgery, by AGI Labs. Measured locally. Nothing was applied to a live setup.</span>
</footer>
</div>
<script id="result-data" type="application/json">{payload}</script>
<script>{asset('charts.js')}</script>
<script>{asset('cloud.js')}</script>
<script>
(function () {{
  var el = document.getElementById('result-data');
  if (!el) return;
  var result;
  try {{ result = JSON.parse(el.textContent); }} catch (e) {{ return; }}

  // Charts are progressive enhancement. If the chart bundle did not ship, the
  // mount is removed rather than left as an empty framed box that reads as a
  // chart that failed to load.
  document.querySelectorAll('[data-chart]').forEach(function (mount) {{
    var fn = window.BSCharts && window.BSCharts[mount.dataset.chart];
    if (typeof fn !== 'function') {{
      var block = mount.closest('.chart-block');
      if (block) block.remove();
      return;
    }}
    try {{ fn(mount, result, {{}}); }}
    catch (e) {{ var b = mount.closest('.chart-block'); if (b) b.remove(); }}
  }});

  var cloud = document.querySelector('[data-cloud]');
  if (cloud && window.BSCloud && typeof window.BSCloud.mount === 'function') {{
    try {{
      window.BSCloud.mount(cloud, {{
        clear: ['.hero-copy', '.hero-chart'],
        topInset: 64,
        fadeBottom: 0.35
      }});
    }} catch (e) {{ cloud.remove(); }}
  }}
}})();
</script>
</body></html>'''


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    try:
        raw = validate(json.loads(a.input.read_text()))
    except (OSError, ValueError, TypeError, KeyError) as e:
        p.exit(2, f'Render failed: {e}\n')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(report_html(raw), encoding='utf-8')
    print(f'Wrote {a.out} ({a.out.stat().st_size // 1024} KB). No upload, no live setup changes.')


if __name__ == '__main__':
    main()
