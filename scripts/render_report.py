#!/usr/bin/env python3
"""Render Brain Surgery local/public reports from bounded evaluation results.
Renderer only: no evaluation, upload, install, or live configuration edits.
Python standard library only; all report assets are local.
"""
from __future__ import annotations
import argparse, base64, html, json, math, os
from pathlib import Path
from typing import Any
from brain_visual import brain_svg

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
VARIANT = os.environ.get('BS_FINDINGS_VARIANT','a').lower()  # temporary: 'a' cards, 'b' paired counts
WORKFLOWS = {
    'presentations': 'Presentations', 'writing': 'Writing', 'coding': 'Coding',
    'research': 'Research', 'spreadsheets': 'Spreadsheets', 'design': 'Design', 'other': 'Other work'
}
FINDINGS = {
    'invocation': ('Useful skill, wrong timing.', 'Helped when tested. Your agent did not reach it.'),
    'conflict': ('Two instructions are fighting.', 'A simpler path performed better.'),
    'keep': ('Already working.', 'Leave it alone.'),
    'unknown': ('Not enough evidence.', 'Could not measure this cleanly.'),
}
MARK = '<svg class="edge-logo" viewBox="0 0 100 66.6667" aria-hidden="true"><path d="M 0 50 A 50 50 0 0 1 100 50 L 100 66.6667 L 0 66.6667 Z" fill="currentColor"/></svg>'
ICONS = {
    'lock':'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    'arrow':'<path d="M5 12h14m-5-5 5 5-5 5"/>',
    'share':'<path d="M8 5H5v14h14v-3M12 4h8v8M20 4 10 14"/>',
    'globe':'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
}

def icon(name: str) -> str:
    return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">' + ICONS[name] + '</svg>'

def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()

def safejson(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, separators=(',', ':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')

def finite_int(v: Any, key: str, low=0, high=100000) -> int:
    if type(v) is not int or not low <= v <= high:
        raise ValueError(f'{key} must be an integer from {low} to {high}')
    return v

def check_trials(t: Any, task_id: str) -> None:
    """A trials block is a count of runs, so it has to survive being counted.

    Rejected rather than ignored: a malformed block that silently falls back to
    task-level scoring would change the denominator of the headline without
    anything on the page saying so.
    """
    if not isinstance(t, dict): raise ValueError(f'{task_id}: trials must be an object')
    for side in ('before','after'):
        s = t.get(side)
        if not isinstance(s, dict): raise ValueError(f'{task_id}: trials.{side} must be an object')
        passed, total = s.get('passed'), s.get('total')
        if type(passed) is not int or type(total) is not int:
            raise ValueError(f'{task_id}: trials.{side} needs integer passed/total')
        if not 0 <= passed <= total or total < 1:
            raise ValueError(f'{task_id}: trials.{side} needs 0 <= passed <= total, total >= 1')

def side_totals(pairs: list[dict[str, Any]], side: str) -> tuple[int,int]:
    return (sum(p['trials'][side]['passed'] for p in pairs),
            sum(p['trials'][side]['total'] for p in pairs))

def summarize_model_comparison(raw: dict[str, Any], tasks: int) -> dict[str, Any] | None:
    grid = raw.get('model_comparison')
    if grid is None:
        return None
    if not isinstance(grid, dict) or grid.get('illustrative') is not True or raw.get('example') is not True:
        raise ValueError('model_comparison is supported only for an explicitly illustrative example')
    total = finite_int(grid.get('tasks'), 'model_comparison.tasks', 1, 1000)
    if total != tasks:
        return None
    pairs = [p for p in raw.get('pairs', []) if p.get('valid') is True]
    if len(pairs) != total:
        return None
    result = {'illustrative': True, 'tasks': total}
    for key in ('current_model', 'comparison_model'):
        row = grid.get(key)
        if not isinstance(row, dict):
            raise ValueError(f'model_comparison.{key} must be an object')
        if key == 'current_model':
            current = sum(p['before'] for p in pairs)
            tested = sum(p['after'] for p in pairs)
        else:
            if any(type(p.get('comparison_current')) is not bool or type(p.get('comparison_tested')) is not bool for p in pairs):
                raise ValueError('every illustrative pair needs comparison_current/comparison_tested booleans')
            current = sum(p['comparison_current'] for p in pairs)
            tested = sum(p['comparison_tested'] for p in pairs)
        result[key] = {
            'label': str(row.get('label') or key.replace('_', ' ').title()),
            'detail': str(row.get('detail') or 'Illustrative configuration'),
            'current_passed': current,
            'tested_passed': tested,
            'current_percent': math.floor(100 * current / total + .5),
            'tested_percent': math.floor(100 * tested / total + .5),
        }
    return result

def summarize(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get('schema_version') not in {'brain-surgery/0.2','brain-surgery/0.3','brain-surgery/0.4'}:
        raise ValueError('Unsupported schema_version')
    if raw.get('metric_kind') != 'task_pass_rate':
        raise ValueError('Only task_pass_rate is implemented. Do not coerce taste ratings into pass percentages.')
    pairs = raw.get('pairs', [])
    if not isinstance(pairs, list): raise ValueError('pairs must be an array')
    seen, valid = set(), []
    for p in pairs:
        if not isinstance(p, dict) or not isinstance(p.get('task_id'), str): raise ValueError('Each pair needs task_id')
        if p['task_id'] in seen: raise ValueError('Duplicate task_id: repeated trials are not distinct tasks')
        seen.add(p['task_id'])
        if p.get('workflow') not in WORKFLOWS: raise ValueError('Unknown workflow')
        if type(p.get('valid')) is not bool: raise ValueError('Each pair needs boolean valid')
        if p['valid']:
            if type(p.get('before')) is not bool or type(p.get('after')) is not bool:
                raise ValueError('Valid pairs need boolean before/after')
            if 'trials' in p: check_trials(p['trials'], p['task_id'])
            valid.append(p)
    n = len(valid)
    # Trials change the denominator, not the sample. Six tasks scored as six
    # booleans means one flipped task moves the headline by 16.7 points, which is
    # larger than the effect being measured. When every valid pair reports its
    # trials, the percentage is passes over trials and the page still says six
    # tasks, because six tasks is what was tested.
    trialled = bool(valid) and all('trials' in p for p in valid)
    if trialled:
        before, before_total = side_totals(valid, 'before')
        after, after_total = side_totals(valid, 'after')
        unit = 'trials'
    else:
        before, before_total = sum(p['before'] for p in valid), n
        after, after_total = sum(p['after'] for p in valid), n
        unit = 'tasks'
    adequate = n >= 2 and before_total > 0 and after_total > 0
    # Rates, not counts. The two sides can carry different trial totals when a
    # run is dropped on one side only, and comparing raw counts across unequal
    # denominators is how a smaller sample turns into a worse result.
    before_rate = 100.0*before/before_total if adequate else None
    after_rate = 100.0*after/after_total if adequate else None
    state = 'insufficient' if not adequate else ('improved' if after_rate > before_rate else ('unchanged' if after_rate == before_rate else 'degraded'))
    buckets = []
    for key, label in WORKFLOWS.items():
        xs = [p for p in valid if p['workflow'] == key]
        if not xs: continue
        eligible = [p for p in xs if p.get('invocation',{}).get('eligible') is True]
        known = [p for p in eligible if type(p['invocation'].get('before')) is bool and type(p['invocation'].get('after')) is bool]
        inv = {'opportunities':len(eligible),'observed':len(known),'before':sum(p['invocation']['before'] for p in known),'after':sum(p['invocation']['after'] for p in known)}
        if trialled:
            wb, wbt = side_totals(xs, 'before'); wa, wat = side_totals(xs, 'after')
        else:
            wb, wbt = sum(p['before'] for p in xs), len(xs)
            wa, wat = sum(p['after'] for p in xs), len(xs)
        buckets.append({'key':key,'label':label,'tasks':len(xs),'before':wb,'after':wa,
                        'before_total':wbt,'after_total':wat,'invocation':inv})
    # Condition C from the methodology: the same held-out tasks run on a stronger
    # model with the *current* setup. Optional, because a run without it is still
    # a valid result; absent is rendered as "not measured", never as zero.
    ml = raw.get('model_lift')
    if ml is not None and (type(ml) not in (int,float) or not -100 <= ml <= 100):
        raise ValueError('model_lift must be a number of points from -100 to 100')
    model_lift = float(ml) if ml is not None else None
    stronger_model = raw.get('stronger_model') if raw.get('stronger_model') in {
        'Claude', 'GPT', 'Qwen', 'Gemini', 'Other', 'Not shared'
    } else None
    if model_lift is not None and not stronger_model:
        raise ValueError('model_lift needs stronger_model: an unnamed model is not a comparison')
    # Paired counts. The aggregate hides whether the candidate fixed failures or
    # traded one task for another, which is the difference between a safe change
    # and a lucky one.
    improved_tasks = unchanged_tasks = regressed_tasks = 0
    for p in valid:
        if trialled:
            b = p['trials']['before']['passed']/p['trials']['before']['total']
            a_ = p['trials']['after']['passed']/p['trials']['after']['total']
        else:
            b, a_ = float(p['before']), float(p['after'])
        if a_ > b: improved_tasks += 1
        elif a_ < b: regressed_tasks += 1
        else: unchanged_tasks += 1
    model_label = raw.get('model_family','Not shared')
    if model_label not in {'Claude','GPT','Qwen','Gemini','Other','Not shared'}: model_label = 'Not shared'
    fixes = []
    for f in raw.get('finding_codes',[]):
        if f not in FINDINGS: raise ValueError('Unknown finding code')
        if f not in fixes: fixes.append(f)
    if state != 'improved': fixes = ['keep' if state == 'unchanged' else 'unknown']
    return {
        'schema_version':'brain-surgery-public/0.4','example':bool(raw.get('example',False)),
        'state':state,'tasks':n,'invalid_pairs':len(pairs)-n,'before_passes':before,'after_passes':after,
        'unit':unit,'before_total':before_total,'after_total':after_total,
        'improved_tasks':improved_tasks,'unchanged_tasks':unchanged_tasks,'regressed_tasks':regressed_tasks,
        'model_lift':model_lift,'stronger_model':stronger_model,
        'before_percent':math.floor(before_rate+.5) if adequate else None,
        'after_percent':math.floor(after_rate+.5) if adequate else None,
        'delta_points':(after_rate-before_rate) if adequate else None,
        'workflows':buckets,'workflow_count':len(buckets),'skills_inspected':finite_int(raw.get('skills_inspected',0),'skills_inspected'),
        'finding_codes':fixes[:3],'method_version':'paired-tasks/0.4','model_family':model_label,
        'evaluator_type':raw.get('evaluator_type') if raw.get('evaluator_type') in {'fixed_checks','human_checklist','model_judge','mixed'} else 'mixed',
        'change_status':'not_applied','source':'locally_reported'
    }

def state_copy(s: dict[str, Any]) -> tuple[str,str,str]:
    if s['state'] == 'improved':
        pts = int(round(s['delta_points'] or 0))
        unit = 'point' if abs(pts) == 1 else 'points'
        sub = f'{s["after_passes"]}/{s["after_total"]} {s["unit"]} passed, against {s["before_passes"]}/{s["before_total"]} before.'
        return f'Your setup left {pts} {unit} on the table.', sub, 'Tested · not applied'
    if s['state'] == 'unchanged':
        return 'No measurable setup win found.', 'The current setup matched the tested candidate.', 'Keep current setup'
    if s['state'] == 'degraded':
        return 'The current setup won this round.', 'The tested candidate made fewer tasks pass.', 'Keep current setup'
    return 'Not enough evidence to score this yet.', 'The scan found useful clues, but not enough comparable tasks.', 'Incomplete scan'

def social_svg(s: dict[str, Any]) -> str:
    scored = s['before_percent'] is not None and s['after_percent'] is not None
    before = str(s['before_percent']) if scored else ''
    after = str(s['after_percent']) if scored else ''
    art = brain_svg(
        100*s['before_passes']/s['before_total'] if scored else None,
        100*s['after_passes']/s['after_total'] if scored else None,
        prefix='social-brain'
    ).replace('viewBox=\"0 0 440 438\"','x=\"802\" y=\"139\" width=\"325\" height=\"320\" viewBox=\"0 20 440 380\"')
    sample = 'ILLUSTRATIVE DESIGN EXAMPLE · NOT A MEASURED SCAN' if s['example'] else ''
    if s['state']=='improved' and s['regressed_tasks']:
        line1, line2 = 'Higher overall.', 'Some work got worse.'
        detail = f'+{int(round(s["delta_points"] or 0))} points overall · {s["regressed_tasks"]} regressed · Same model'
        verdict = 'Promising, not safe to apply as-is · Tested, not applied'
    elif s['state']=='improved':
        line1, line2 = 'Same AI.', 'Better on this test.'
        detail = f'+{int(round(s["delta_points"] or 0))} points · {s["tasks"]} tasks · Same model'
        verdict = f'{s["improved_tasks"]} improved · {s["regressed_tasks"]} worsened · Tested, not applied'
    elif s['state']=='unchanged':
        line1, line2 = 'Same AI.', 'Same measured result.'
        detail = f'0 points · {s["tasks"]} tasks · Same model'
        verdict = 'No measurable setup win · Keep current setup'
    elif s['state']=='degraded':
        line1, line2 = 'Current setup.', 'Better on this test.'
        detail = f'{int(round(s["delta_points"] or 0))} points · {s["tasks"]} tasks · Same model'
        verdict = f'{s["regressed_tasks"]} worsened · Keep current setup'
    else:
        line1, line2 = 'Not enough evidence.', 'No comparison score yet.'
        detail = 'SCAN INCOMPLETE · MORE COMPARABLE TASKS NEEDED'
        verdict = 'Missing pairs are not zeros · Nothing applied'
    score = (f'<text x="50" y="364" fill="#050505" font-size="119" font-weight="550" letter-spacing="-7">{before}<tspan font-size="46" letter-spacing="-1">%</tspan></text><path d="M300 323h52m-16-16 17 16-17 16" stroke="#aaa" stroke-width="3" fill="none"/><text x="393" y="364" fill="#154cff" font-size="119" font-weight="550" letter-spacing="-7">{after}<tspan font-size="46" letter-spacing="-1">%</tspan></text><text x="57" y="403" fill="#777" font-size="15">Current setup</text><text x="398" y="403" fill="#154cff" font-size="15">With surgery</text>' if scored else '<text x="55" y="365" fill="#777" font-size="32" letter-spacing="-.8">NOT SCORED</text>')
    aria = f'Brain Surgery by AGI Labs. {line1} {line2} ' + (f'Current {before} percent, tested {after} percent. ' if scored else 'No comparison score. ') + verdict
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="{html.escape(aria)}"><rect width="1200" height="630" fill="white"/><g fill="#154cff" opacity=".12"><rect x="770" y="62" width="3" height="3"/><rect x="842" y="94" width="3" height="3"/><rect x="914" y="54" width="3" height="3"/><rect x="986" y="118" width="3" height="3"/><rect x="1058" y="78" width="3" height="3"/><rect x="1130" y="142" width="3" height="3"/></g><g font-family="Inter,-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif"><g transform="translate(52 42) scale(.42)" fill="#050505"><path d="M 0 50 A 50 50 0 0 1 100 50 L 100 66.6667 L 0 66.6667 Z"/></g><text x="102" y="67" fill="#050505" font-size="25" font-weight="650" letter-spacing="-.8">agi labs</text><text x="208" y="65" fill="#777" font-size="14">Brain Surgery</text><text x="55" y="145" fill="#777" font-size="12" letter-spacing="1.6">A SHARED BRAIN SCAN</text><text x="52" y="205" fill="#050505" font-size="48" font-weight="500" letter-spacing="-2"><tspan x="52">{html.escape(line1)}</tspan><tspan x="52" dy="52">{html.escape(line2)}</tspan></text>{score}<text x="55" y="464" fill="#333" font-size="17">{html.escape(detail)}</text><text x="55" y="492" fill="#777" font-size="13">{html.escape(verdict)}</text><path d="M55 527H1145" stroke="#e5e5e5"/><text x="55" y="568" fill="#050505" font-size="22" letter-spacing="-.6">What could your AI gain?</text><text x="1145" y="567" text-anchor="end" fill="#154cff" font-size="17">github.com/agilabs-ai</text><text x="55" y="610" fill="#999" font-size="10" letter-spacing="1">{sample}</text></g>{art}</svg>'''

def breakdown_section(s: dict[str, Any]) -> str:
    rows = []
    for w in ([] if s['state'] == 'insufficient' else s['workflows']):
        n,a,b = w['before_total'],w['before'],w['after']; delta=b-a
        verdict = 'Improved in test' if delta > 0 else ('No change' if delta == 0 else 'Current setup won')
        tone = 'positive' if delta > 0 else ('neutral' if delta == 0 else 'negative')
        inv=w.get('invocation',{}); observed=inv.get('observed',0)
        inv_text=f"{inv.get('before',0)}/{observed} → {inv.get('after',0)}/{observed}" if observed else 'Not measured'
        inv_note='relevant tasks with comparable traces' if observed else 'no comparable loading trace'
        marks=[]
        for count,cls,label in [(a,'baseline','Current'),(b,'candidate','Tested')]:
            segs=''.join(f'<span class="segment {cls if i<count else "empty"}" aria-hidden="true"></span>' for i in range(n))
            marks.append(f'<div class="bar-line"><span class="bar-label">{label}</span><div class="segments">{segs}</div><strong>{count}/{n}</strong></div>')
        rows.append(f'<article class="workflow-row"><div class="workflow-name"><h3>{w["label"]}</h3><span class="result-tag {tone}">{verdict}</span></div><div class="workflow-score" aria-label="{w["label"]}: {a} of {n} current tasks passed, {b} of {n} tested tasks passed">{"".join(marks)}</div><div class="workflow-invocation"><span>Skill reached</span><strong>{inv_text}</strong><small>{inv_note}</small></div></article>')
    if not rows:
        return '<section class="breakdown"><div class="section-heading"><div><p class="eyebrow">INSIDE THE SCAN</p><h2>No comparable tests yet.</h2></div></div></section>'
    return '<section class="breakdown" aria-labelledby="breakdown-title"><div class="section-heading"><div><p class="eyebrow">INSIDE THE SCAN</p><h2 id="breakdown-title">Where the difference came from.</h2></div><p>Same tasks. Same model.</p></div><div class="workflow-table">'+''.join(rows)+'</div><p class="breakdown-note">One block = one tested task. Skill loading is shown separately from task success. Results reflect the full tested change set.</p></section>'

def modal(id: str, title: str, sub: str, body: str) -> str:
    return f'<dialog class="modal" id="{id}" aria-labelledby="{id}-title"><div class="modal-in"><div class="modal-head"><div><h2 id="{id}-title">{title}</h2><p>{sub}</p></div><button class="close" data-close aria-label="Close dialog">×</button></div>{body}</div></dialog>'

def finding_context(code: str, s: dict[str, Any]) -> str:
    """Name the workflow a finding came from, or nothing.

    Derived from the measured buckets, never assigned by position: a label that
    does not follow from the numbers would be a caption, not a finding.
    """
    ws = s['workflows']
    def rate(x, side):
        t = x[f'{side}_total']
        return x[side]/t if t else None
    if code == 'invocation':
        xs = [x for x in ws if x['invocation']['after'] > x['invocation']['before']]
    elif code == 'conflict':
        xs = sorted((x for x in ws if (rate(x,'after') or 0) > (rate(x,'before') or 0)),
                    key=lambda x: (rate(x,'after') or 0)-(rate(x,'before') or 0), reverse=True)
    elif code == 'keep':
        xs = [x for x in ws if rate(x,'after') == rate(x,'before')]
    else:
        xs = []
    return xs[0]['label'] if xs else ''

def lift_section(s: dict[str, Any]) -> str:
    """Setup lift beside model lift. The score alone says nothing about what it cost.

    Model lift is deliberately not folded into the Brain Score: it is the
    reference point the score is read against, not part of it.
    """
    if s['state'] != 'improved' or s['delta_points'] is None: return ''
    setup = int(round(s['delta_points']))
    if s['model_lift'] is None:
        right = '<span class="lift-none">Not measured</span>'
        note = 'Run the same held-out tasks on a stronger model to measure this.'
    else:
        m = int(round(s['model_lift']))
        right = f'<span class="lift-num">{m:+d}</span>'
        note = (f'Changing the setup beat moving to {html.escape(s["stronger_model"])} on the same tasks.'
                if setup > m else
                f'Moving to {html.escape(s["stronger_model"])} beat changing the setup on the same tasks.')
    return ('<section class="lift" aria-labelledby="lift-title">'
            '<h2 id="lift-title">What moved the needle.</h2>'
            '<div class="lift-rows">'
            f'<div class="lift-row"><span>Setup change</span><span class="lift-num on">{setup:+d}</span></div>'
            f'<div class="lift-row"><span>Model upgrade</span>{right}</div>'
            f'</div><p class="lift-note">{note} Points are held-out task pass rate.</p></section>')

def model_matrix_section(raw: dict[str, Any] | None, s: dict[str, Any]) -> str:
    grid = summarize_model_comparison(raw or {}, s['tasks']) if raw else None
    if not grid:
        return ''
    current, comparison, total = grid['current_model'], grid['comparison_model'], grid['tasks']
    setup_lift = current['tested_percent'] - current['current_percent']
    model_alone = comparison['current_percent'] - current['current_percent']
    model_after = comparison['tested_percent'] - current['tested_percent']
    return f'''<section class="report-section" id="model-comparison"><div class="section-head"><div><p class="kicker">MODEL × SETUP</p><h2>Would a different model help?</h2></div><span class="sample-pill">Illustrative example</span></div><div class="model-grid"><div class="model-header">Same six tasks</div><div class="model-header">Current setup</div><div class="model-header blue">With surgery</div><div class="model-name"><strong>{html.escape(current['label'])}</strong><small>{html.escape(current['detail'])}</small></div><div class="model-score">{current['current_percent']}<small>% · {current['current_passed']}/{total}</small></div><div class="model-score tested">{current['tested_percent']}<small>% · {current['tested_passed']}/{total}</small></div><div class="model-name"><strong>{html.escape(comparison['label'])}</strong><small>{html.escape(comparison['detail'])}</small></div><div class="model-score">{comparison['current_percent']}<small>% · {comparison['current_passed']}/{total}</small></div><div class="model-score tested">{comparison['tested_percent']}<small>% · {comparison['tested_passed']}/{total}</small></div></div><div class="model-footer"><span>Setup change <b class="blue">{setup_lift:+d} points</b></span><span>Model change alone <b>{model_alone:+d} points</b></span><span>Model change after surgery <b>{model_after:+d} points</b></span></div><p class="note" style="margin-top:14px">In this fictional example, the setup change makes the bigger difference. One coding task still fails in every condition.</p></section>'''

def example_work_section(raw: dict[str, Any] | None, strict: bool = False) -> str:
    work = (raw or {}).get('example_work')
    if not isinstance(work, dict) or work.get('illustrative') is not True:
        return ''
    pair = next((p for p in (raw or {}).get('pairs', [])
                 if p.get('valid') is True and p.get('task_id') == work.get('task_id')), None)
    if not pair or pair.get('before') is not False or pair.get('after') is not True:
        if strict:
            raise ValueError('example_work must reference an existing task that changed from fail to pass')
        return ''
    if work.get('before') != pair.get('output_before') or work.get('after') != pair.get('output_after'):
        if strict:
            raise ValueError('example_work must reuse the referenced task outputs exactly')
        return ''
    return f'''<section class="report-section" id="example-work"><div class="section-head"><div><p class="kicker">INSPECTED WORK · ILLUSTRATIVE</p><h2>Same request. Better work.</h2></div></div><div class="output-pair"><article class="output-panel"><div class="output-top"><span>CURRENT SETUP</span><span class="output-score">DID NOT PASS</span></div><div class="output-body"><div class="doc-kicker">{html.escape(work.get('label', 'Example output').upper())}</div><p>{html.escape(work.get('before', ''))}</p></div></article><article class="output-panel blue-frame"><div class="output-top"><span>WITH SURGERY</span><span class="output-score">PASSED</span></div><div class="output-body"><div class="doc-kicker">{html.escape(work.get('label', 'Example output').upper())}</div><p>{html.escape(work.get('after', ''))}</p></div></article></div><p class="note" style="margin-top:14px">{html.escape(work.get('finding', ''))}</p></section>'''

def report_html(s: dict[str, Any], raw: dict[str, Any] | None = None, public_source='', complete_demo=False) -> str:
    """Render the measured comparison in the approved AGI Labs presentation.

    The approved prototype is presentation-only; this renderer deliberately
    rebuilds that structure from the allowlisted summary instead of shipping
    its fixture data. Private task evidence and the proposed change plan are
    added only to the local report.
    """
    local = raw is not None and not complete_demo
    detailed = local or complete_demo
    demo = s['example']
    before = s['before_percent']
    after = s['after_percent']
    before_text = '·' if before is None else str(before)
    after_text = '·' if after is None else str(after)
    before_score = '·' if before is None else f'{before}<small>%</small>'
    after_score = '·' if after is None else f'{after}<small>%</small>'
    delta = int(round(s['delta_points'] or 0)) if s['delta_points'] is not None else 0
    headline, subline, status = state_copy(s)
    has_regressions = s['regressed_tasks'] > 0
    if s['state'] == 'improved' and has_regressions:
        local_hero = 'The tested setup passed more overall, but some work got worse.'
        rate_copy = f'<span>{after_text}% passed overall,</span> up from {before_text}%.'
        public_title = 'Higher overall.<br><span class="blue">Some work got worse.</span>'
        public_sub = f'Aggregate pass rate rose from {before_text}% to {after_text}%,<br>but {s["regressed_tasks"]} task{"s" if s["regressed_tasks"] != 1 else ""} regressed.'
        conclusion_title = 'Promising overall.<br>Not safe to apply as-is.'
        conclusion_note = 'Review every regression and retest a revised bundle before considering application.'
    elif s['state'] == 'improved':
        local_hero = headline
        rate_copy = f'<span>{after_text}% passed,</span> up from {before_text}%.'
        public_title = 'Same AI.<br><span class="blue">Better on this test.</span>'
        public_sub = f'{after_text}% of tested {html.escape(s["unit"])} passed,<br>up from {before_text}%.'
        conclusion_title = 'The tested setup did better<br>without changing the model.'
        conclusion_note = 'Review the tested edits with your agent. Applying the full tested bundle is unavailable in this report.'
    elif s['state'] == 'unchanged':
        local_hero = 'The tested setup did not change the measured result.'
        rate_copy = f'<span>Both setups passed {after_text}%</span> of tested {html.escape(s["unit"])}.'
        public_title = 'Same AI.<br><span class="blue">Same measured result.</span>'
        public_sub = f'Both setups passed {after_text}% of tested {html.escape(s["unit"])}.'
        conclusion_title = 'No measurable setup win<br>was found in this test.'
        conclusion_note = 'Keep the current setup. A different candidate needs a separate paired test.'
    elif s['state'] == 'degraded':
        local_hero = 'The current setup performed better on this test.'
        rate_copy = f'<span>The tested setup fell to {after_text}%</span> from {before_text}%.'
        public_title = 'Current setup.<br><span class="blue">Better on this test.</span>'
        public_sub = f'The tested setup fell from {before_text}% to {after_text}% of tested {html.escape(s["unit"])}.'
        conclusion_title = 'Keep the current setup.'
        conclusion_note = 'The candidate performed worse. Do not apply it.'
    else:
        local_hero = 'Not enough comparable work to score this yet.'
        rate_copy = '<span>No defensible before-and-after rate.</span>'
        public_title = 'Not enough evidence.<br><span class="blue">No comparison score yet.</span>'
        public_sub = 'More complete task pairs are needed before comparing setups.'
        conclusion_title = 'Complete more comparable tasks<br>before making a setup decision.'
        conclusion_note = 'Missing comparisons are not zeros. No tested change should be applied from this result.'
    delta_meta = '<b>Not scored</b> · incomplete comparison' if s['state'] == 'insufficient' else f'<b>{delta:+d} points</b> on tested work'
    method_score = 'Not scored · incomplete comparison' if s['state'] == 'insufficient' else f'{before_text}% → {after_text}%'
    brain = brain_svg(
        100*s['before_passes']/s['before_total'] if before is not None else None,
        100*s['after_passes']/s['after_total'] if after is not None else None,
        prefix='approved-report-brain'
    )
    brand_mark = MARK
    workflow_rows = []
    public_workflows = []
    for w in ([] if s['state'] == 'insufficient' else s['workflows']):
        bp = round(100*w['before']/w['before_total']) if w['before_total'] else 0
        ap = round(100*w['after']/w['after_total']) if w['after_total'] else 0
        d = ap-bp
        workflow_rows.append(f'''<div class="workflow-line"><span class="workflow-name">{html.escape(w['label'])}</span><span class="workflow-n">{w['tasks']}</span><span class="value-bar"><span class="bar-track"><i style="width:{bp}%"></i></span><b>{bp}%</b></span><span class="value-bar tested"><span class="bar-track"><i style="width:{ap}%"></i></span><b>{ap}%</b></span><span class="delta{' zero' if d == 0 else ''}">{d:+d}</span><span aria-hidden="true"></span></div>''')
        public_workflows.append(f'<div class="public-workflow"><p class="kicker">{html.escape(w["label"])}</p><strong>{bp}% <span>→ {ap}%</span></strong><p>{w["tasks"]} tested task{"s" if w["tasks"] != 1 else ""}</p></div>')
    result_summary = ('More complete task pairs are needed for a defensible comparison.' if s['state'] == 'insufficient'
                      else f'{s["after_passes"]} of {s["after_total"]} {s["unit"]} passed with the tested setup.')
    paired = f'''<section class="result-summary"><div><strong>{result_summary}</strong><p>{s['before_passes']}/{s['before_total']} → {s['after_passes']}/{s['after_total']} {s['unit']} passed</p></div><div class="result-flags"><span><b>{s['improved_tasks']}</b> improved</span><span><b>{s['unchanged_tasks']}</b> unchanged</span><span><b>{s['regressed_tasks']}</b> worsened</span></div></section>'''
    changes = ''
    test_evidence = ''
    change_rows = []
    if detailed:
        evidence_rows = []
        for pair in raw.get('pairs', []):
            valid_pair = pair.get('valid') is True
            if not valid_pair:
                current = tested = 'Not scored'
                evidence = 'Excluded: ' + str(pair.get('invalid_reason') or 'comparison incomplete')
            elif 'trials' in pair:
                current = f"{pair['trials']['before']['passed']}/{pair['trials']['before']['total']} trials"
                tested = f"{pair['trials']['after']['passed']}/{pair['trials']['after']['total']} trials"
                evidence = 'Repeated trials reported'
            else:
                current = 'Passed' if pair.get('before') else 'Did not pass'
                tested = 'Passed' if pair.get('after') else 'Did not pass'
                evidence = 'Task-level pass check'
            if valid_pair:
                checks = pair.get('checks') or {}
                check_parts = []
                for side in ('before', 'after'):
                    rows = checks.get(side) or []
                    if rows:
                        check_parts.append(f"{side}: {sum(r.get('passed') is True for r in rows)}/{len(rows)} checks")
                invocation = pair.get('invocation') or {}
                if invocation.get('eligible') is True:
                    before_loaded, after_loaded = invocation.get('before'), invocation.get('after')
                    load = lambda value: 'loaded' if value is True else ('not loaded' if value is False else 'unknown')
                    check_parts.append(f"skill: {load(before_loaded)} → {load(after_loaded)}")
                evidence = '; '.join(check_parts) or evidence
            title = html.escape(str(pair.get('title') or pair['task_id']))
            if complete_demo:
                labels = pair.get('acceptance_checks', [])
                before_checks = pair.get('checks_before', [])
                after_checks = pair.get('checks_after', [])
                if not isinstance(labels, list) or not labels or len(before_checks) != len(labels) or len(after_checks) != len(labels):
                    raise ValueError(f'{pair["task_id"]}: illustrative acceptance checks need aligned before/after outcomes')
                if any(type(value) is not bool for value in before_checks + after_checks):
                    raise ValueError(f'{pair["task_id"]}: illustrative check outcomes must be boolean')
                checks = ''.join(
                    f'<li><span>{html.escape(str(label))}</span><span class="mono">Current: {"Pass" if before_checks[i] else "Fail"} · Surgery: {"Pass" if after_checks[i] else "Fail"}</span></li>'
                    for i, label in enumerate(labels)
                )
                four = [('Current model / current setup', pair.get('before')),
                        ('Current model / surgery', pair.get('after')),
                        ('Comparison model / current setup', pair.get('comparison_current')),
                        ('Comparison model / surgery', pair.get('comparison_tested'))]
                outcomes = ' · '.join(f'{label}: {"Pass" if value is True else "Fail"}' for label, value in four)
                detail = (f'<details class="req-detail"><summary>{title}</summary><div class="inside">'
                          f'<p><strong>Request</strong><br>{html.escape(str(pair.get("request", "")))}</p>'
                          f'<p><strong>Acceptance checks</strong></p><ul>{checks}</ul>'
                          f'<p><strong>Current output</strong><br>{html.escape(str(pair.get("output_before", "")))}</p>'
                          f'<p><strong>With surgery</strong><br>{html.escape(str(pair.get("output_after", "")))}</p>'
                          f'<p class="mono">{html.escape(outcomes)}</p></div></details>')
            else:
                detail = title
            evidence_rows.append(
                f'<tr><td>{detail}</td>'
                f'<td>{html.escape(WORKFLOWS.get(pair.get("workflow"), "Other work"))}</td>'
                f'<td>{current}</td><td>{tested}</td><td>{html.escape(evidence)}</td></tr>')
        table = (f'''<div class="table-scroll"><table class="data-table"><thead><tr><th>Task</th><th>Workflow</th><th>Current</th><th>Tested</th><th>Checks / invocation</th></tr></thead><tbody>{''.join(evidence_rows)}</tbody></table></div>'''
                 if evidence_rows else '<p class="note">No task pairs were recorded. There is nothing to score or apply.</p>')
        evidence_label = 'TEST EVIDENCE · ILLUSTRATIVE' if complete_demo else 'TEST EVIDENCE · LOCAL ONLY'
        evidence_note = ('Fictional tasks and outcomes shown to demonstrate the evidence experience.' if complete_demo else
                         f'{s["invalid_pairs"]} invalid pair{"s" if s["invalid_pairs"] != 1 else ""} excluded. Task names, check outcomes, invocation evidence, and exclusion reasons stay local.')
        test_evidence = f'''<section class="report-section" id="report-tests"><div class="section-head"><div><p class="kicker">{evidence_label}</p><h2>The tasks behind the result.</h2></div></div>{table}<p class="note" style="margin-top:14px">{evidence_note}</p></section>'''
        for i,c in enumerate(raw.get('plan',{}).get('changes',[]),1):
            before_instruction = str(c.get('before_instruction', ''))
            after_instruction = str(c.get('after_instruction', ''))
            affected_tasks = c.get('affected_tasks', [])
            if complete_demo and (not before_instruction or not after_instruction or not isinstance(affected_tasks, list) or not affected_tasks):
                raise ValueError('illustrative changes need exact before/after instructions and affected tasks')
            edit_detail = (f'<div class="edit-review"><p class="kicker">BEFORE</p><code>{html.escape(before_instruction)}</code>'
                           f'<p class="kicker blue">AFTER</p><code>{html.escape(after_instruction)}</code>'
                           f'<p><strong>Affected tasks:</strong> {html.escape(", ".join(map(str, affected_tasks)))}</p></div>'
                           if before_instruction and after_instruction else
                           f'<code class="change-path">{html.escape(c.get("patch_preview", ""))}</code>')
            change_rows.append(f'''<article class="change-line"><span class="change-no">{i:02d}</span><div><div class="change-title">{html.escape(c.get('title','Proposed edit'))}</div></div><p class="change-why">{html.escape(c.get('description',''))}</p><details><summary class="text-link">View exact edit</summary>{edit_detail}</details></article>''')
        if change_rows:
            changes=f'''<section class="report-section" id="report-changes"><div class="section-head"><div><p class="kicker">THE SURGERY</p><h2>{len(change_rows)} targeted changes.</h2></div></div><div class="change-list">{''.join(change_rows)}</div><p class="note" style="margin-top:14px;font-size:11px">{'These are illustrative edits. ' if complete_demo else 'Tested together. Provider instructions unchanged. '}Nothing has been changed.</p></section>'''
    workflow_section = (f'''<section class="report-section"><div class="section-head"><div><p class="kicker">WORKFLOWS</p><h2>Where the difference came from.</h2></div></div><div class="workflow-head"><span>Workflow</span><span class="tasks-head">Tasks</span><span>Current</span><span>Tested</span><span class="right">Change</span><span></span></div>{''.join(workflow_rows)}<div class="workflow-end"><p>Changes shown in percentage points. Unchanged and worsened tasks are included.</p></div></section>'''
                        if s['state'] != 'insufficient' else
                        '<section class="report-section"><div class="section-head"><div><p class="kicker">WORKFLOWS</p><h2>Not scored yet.</h2></div></div><p class="note">Workflow percentages are withheld until at least two comparable task pairs are complete.</p></section>')
    method=f'''<section class="report-section" id="report-method"><div class="section-head"><div><p class="kicker">HOW WE TESTED</p><h2>Same task. Same model.<br>With and without the surgery.</h2></div></div><div class="method-figure"><div class="method-input">Your task + files</div><div class="method-fork"></div><div class="method-arms"><div class="method-arm"><div class="kicker">Without the surgery</div><strong>Current setup</strong><small>Existing skills and instructions</small></div><div class="method-arm tested"><div class="kicker blue">With the surgery</div><strong class="blue">Proposed setup</strong><small>With targeted edits</small></div></div><div class="method-join"></div><div class="method-check">Same success checklist</div><div class="mono blue" style="font-size:15px;margin-top:13px">{method_score}</div></div><p class="method-caption">Same task, inputs, model, and checks. Only the setup changes.</p><p class="method-caption">The tested setup has not been applied.</p></section>'''
    location = 'Example report' if complete_demo else ('Private report' if local else 'Shared summary')
    nav_action = ('<a class="text-link" href="/#setup-prompt">Scan my AI →</a>' if complete_demo else
                  ('<button class="text-link" data-action="export-report">Export report</button>' if local else ''))
    nav=f'''<div class="wrap"><nav class="nav" aria-label="Main navigation"><a class="brand" href="/" aria-label="AGI Labs Brain Surgery home">{brand_mark}agi labs<span class="brand-divider"></span><span class="brand-product">Brain Surgery</span></a><div class="nav-links"><span class="location tiny">{location}</span>{nav_action}</div></nav></div>'''
    if detailed:
        if complete_demo:
            primary_action = '<a class="btn btn-dark" href="#report-tests">View the tests</a><a class="btn btn-outline" href="#report-changes">Review the changes</a>'
            report_title = 'An example brain scan'
            report_meta = 'Six fictional tasks · Two model configurations · Nothing applied'
            hero_copy = 'A better setup passed three more tasks.'
        else:
            primary_action = ('<button class="btn btn-dark" data-action="surgery">Review tested changes →</button>'
                              if change_rows and s['state'] == 'improved'
                              else '<a class="btn btn-dark" href="#report-method">Review the evidence →</a>')
            primary_action += '<a class="btn btn-outline" href="#report-tests">View tests</a><button class="btn btn-outline" data-action="share">Export public preview</button>'
            report_title = 'Your brain scan'
            report_meta = f'{s["tasks"]} selected tasks · {html.escape(s["model_family"])}'
            hero_copy = html.escape(local_hero)
        body=f'''{nav}<main class="wrap animate-in"><div class="report-head"><div><h1>{report_title}</h1><p class="tiny">{report_meta}</p></div><span class="status" data-application-status>{'Illustrative example' if complete_demo else status}</span></div><section class="report-hero"><div class="cloud-layer" data-cloud="right" data-intensity="0.31" aria-hidden="true"></div><div class="foreground"><div class="kicker"><span class="dot"></span> {'ILLUSTRATIVE EXAMPLE' if complete_demo else 'YOUR BRAIN SCAN'}</div><h2>{hero_copy}<br>{rate_copy}</h2><div class="hero-measure"><div><div class="report-numbers"><div><div class="report-number">{before_score}</div><div class="number-label">Current setup</div></div><div class="report-arrow">→</div><div><div class="report-number blue">{after_score}</div><div class="number-label">With surgery</div></div></div><p class="score-explainer">{html.escape(subline)}</p></div><div class="brain-wrap">{brain}</div></div><div class="hero-meta"><span>{delta_meta}</span><span><b>Same model</b> and inputs</span><span><b>{s['tasks']} tasks</b> compared</span></div></div></section>{paired}<div class="report-actions">{primary_action}<span class="note">{'Fictional results; not a measurement.' if complete_demo else 'Your live setup is unchanged.'}</span></div>{workflow_section}{model_matrix_section(raw, s)}{example_work_section(raw, complete_demo)}{test_evidence}{changes}{method}<section class="report-conclusion"><span class="conclusion-mark">+</span><h2>{'Find out what your setup needs.' if complete_demo else conclusion_title}</h2><p>{'Start with a private, read-only scan. Changes and sharing always need your approval.' if complete_demo else conclusion_note}</p>{'<a class="btn btn-dark" href="/#setup-prompt">Scan my AI →</a>' if complete_demo else ''}</section><footer class="footer"><span>Brain Surgery, by AGI Labs.</span><div><a href="/">Home</a><a href="https://github.com/agilabs-ai/brain-surgery" target="_blank" rel="noreferrer">Source ↗</a></div></footer></main>'''
    else:
        body=f'''{nav}<main class="small-wrap animate-in"><section class="public-hero"><div class="cloud-layer" data-cloud="sides" data-intensity="0.52" aria-hidden="true"></div><div class="foreground"><div class="case-person" style="justify-content:center"><span class="avatar fd">AI</span><span class="kicker">A SHARED BRAIN SCAN</span></div><h1>{public_title}</h1><p class="public-sub">{public_sub}</p><div class="public-graphic"><div><div class="stat-big">{before_score}</div><div class="stat-label">Current</div></div><div>{brain}</div><div><div class="stat-big blue">{after_score}</div><div class="stat-label">With surgery</div></div></div><div class="public-meta">{s['tasks']} personal tasks · Same model · {s['workflow_count']} workflows<br>{s['improved_tasks']} improved · {s['unchanged_tasks']} unchanged · {s['regressed_tasks']} worsened · Tested, not applied</div>{'<div style="margin-top:14px"><span class="sample-pill">Illustrative design example</span></div>' if demo else ''}</div></section><section class="public-convert"><h2>What could your AI gain?</h2><p class="note">Run the same private, paired test on your own work.</p></section><section class="section"><div class="section-head"><div><p class="kicker">INSIDE THE RESULT</p><h2>Where the difference came from.</h2></div></div><div class="public-summary">{''.join(public_workflows)}</div><p class="note" style="margin-top:22px;font-size:11px">Unchanged and worsened tasks included. Prompts, outputs, skill names, paths, and edits stay private.</p></section>{method}<footer class="footer"><span>Brain Surgery, by AGI Labs.</span><div><a href="https://github.com/agilabs-ai/brain-surgery" target="_blank" rel="noreferrer">Source ↗</a></div></footer></main>'''
    css=(ASSETS/'approved-ui.css').read_text() + '''
@media(max-width:640px){.report-actions{flex-wrap:wrap}.report-actions .btn{flex:1 1 calc(50% - 8px)}.report-actions>.note{flex-basis:100%}}
'''
    cloud=(ASSETS/'approved-cloud.js').read_text()
    private_payload={k:raw[k] for k in ('pairs','plan') if k in raw} if local else None
    public_blob=b64(public_source) if local else ''
    scripts=f'''<script id="summary-data" type="application/json">{safejson(s)}</script>{f'<script id="local-data" type="application/json">{safejson(private_payload)}</script><script id="public-source" type="text/plain">{public_blob}</script>' if local else ''}<script>{cloud}</script><script>window.Clouds?.mountAll?.();function save(value,name){{const b=new Blob([value],{{type:'text/html'}}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}}function decodedPublic(){{return Uint8Array.from(atob(document.querySelector('#public-source').textContent),c=>c.charCodeAt(0))}}document.addEventListener('click',e=>{{if(e.target.closest('[data-action="export-report"]'))save(document.documentElement.outerHTML,'brain-surgery-private-report.html');if(e.target.closest('[data-action="share"]'))save(decodedPublic(),'brain-surgery-public-preview.html');if(e.target.closest('[data-action="surgery"]'))document.querySelector('.change-list')?.scrollIntoView({{behavior:'smooth'}});}});</script>'''
    metadata='' if local else f'<meta property="og:type" content="website"><meta property="og:title" content="Brain Surgery by AGI Labs · {html.escape(headline)}"><meta property="og:description" content="{s["tasks"]} tested tasks. Current versus tested setup. Tested, not applied."><meta property="og:image" content="social-card.svg"><meta name="twitter:card" content="summary_large_image">'
    badge='<div class="preview-ribbon">ILLUSTRATIVE DESIGN EXAMPLE · NO AUDIT OR UPLOAD</div>' if demo else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer"><title>Brain Surgery · AGI Labs</title>{metadata}<style>{css}</style></head><body>{badge}{body}{scripts}</body></html>'''

def write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode('utf-8'))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def render(raw: dict[str,Any], out: Path, complete_demo: bool = False) -> dict[str,Any]:
    out.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(out,0o700); s=summarize(raw)
    if complete_demo and not s['example']:
        raise ValueError('complete demo output requires example: true')
    public=report_html(s, raw if complete_demo else None, complete_demo=complete_demo)
    write_private(out/'public-report.html', public)
    write_private(out/'local-report.html', report_html(s,raw,public))
    write_private(out/'social-card.svg', social_svg(s))
    write_private(out/'public-summary.json', json.dumps(s,indent=2))
    return s

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input',required=True,type=Path); p.add_argument('--out',required=True,type=Path); p.add_argument('--complete-demo',action='store_true')
    a=p.parse_args()
    try: raw=json.loads(a.input.read_text()); s=render(raw,a.out,a.complete_demo)
    except (OSError,ValueError,TypeError,KeyError) as e: p.exit(2,f'Render failed: {e}\n')
    print(f'Created local/public HTML and social SVG. State: {s["state"]}. No upload or live setup changes.')
if __name__=='__main__': main()
