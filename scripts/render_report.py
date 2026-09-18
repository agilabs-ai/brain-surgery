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
WORKFLOWS = {
    'presentations': 'Presentations', 'writing': 'Writing', 'coding': 'Coding',
    'research': 'Research', 'spreadsheets': 'Spreadsheets', 'design': 'Design', 'other': 'Other work'
}
FINDINGS = {
    'invocation': ('Useful skill, wrong timing.', 'The skill helped when tested, but your agent did not reliably reach it.'),
    'conflict': ('Two instructions are fighting.', 'A simpler instruction path performed better on the tested work.'),
    'keep': ('This part is already working.', 'The candidate did not improve this workflow. Leave it alone.'),
    'unknown': ('Not enough evidence here.', 'The scan could not measure this part cleanly. No change recommended.'),
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
        return f'Your setup left {pts} {unit} on the table.', f'{s["after_passes"]}/{s["after_total"]} {s["unit"]} passed, against {s["before_passes"]}/{s["before_total"]} before.', 'Tested · not applied'
    if s['state'] == 'unchanged':
        return 'No measurable setup win found.', 'The current setup matched the tested candidate.', 'Keep current setup'
    if s['state'] == 'degraded':
        return 'The current setup won this round.', 'The tested candidate made fewer tasks pass.', 'Keep current setup'
    return 'Not enough evidence to score this yet.', 'The scan found useful clues, but not enough comparable tasks.', 'Incomplete scan'

def social_svg(s: dict[str, Any]) -> str:
    headline, _, status = state_copy(s)
    before = '&middot;' if s['before_percent'] is None else str(s['before_percent'])
    after = '&middot;' if s['after_percent'] is None else str(s['after_percent'])
    art = brain_svg(
        100*s['before_passes']/s['before_total'] if s['before_percent'] is not None else None,
        100*s['after_passes']/s['after_total'] if s['after_percent'] is not None else None,
        prefix='social-brain'
    ).replace('viewBox=\"0 0 440 438\"','x=\"835\" y=\"147\" width=\"300\" height=\"299\" viewBox=\"0 0 440 438\"')
    sample = 'ILLUSTRATIVE DESIGN EXAMPLE' if s['example'] else ''
    trials_note = f' · {s["before_total"]}+{s["after_total"]} TRIALS' if s['unit']=='trials' else ''
    meta = f'{s["tasks"]} TASKS{trials_note} · {s["workflow_count"]} WORKFLOWS · SAME MODEL' if s['tasks'] >= 2 else 'SCAN INCOMPLETE · MORE COMPARABLE TASKS NEEDED'
    if s['state']=='improved':
        pts=int(round(s['delta_points'] or 0)); unit='point' if abs(pts)==1 else 'points'
        line1=f'Your setup left {pts} {unit}'
        line2='on the table.'
    elif s['state']=='unchanged':
        line1='No measurable setup win'
        line2='found.'
    elif s['state']=='degraded':
        line1='The current setup won'
        line2='this round.'
    else:
        line1='Not enough evidence'
        line2='to score this yet.'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="Brain Surgery by AGI Labs. {html.escape(headline)} Current {before} percent, tested {after} percent. {status}.">
<rect width="1200" height="630" fill="#ffffff"/>
<path d="M0 628H600" stroke="#050505" stroke-width="4"/><path d="M600 628H1200" stroke="#154CFF" stroke-width="4"/>
<g font-family="Inter,-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">
  <g transform="translate(57 44) scale(.42)" fill="#050505"><path d="M 0 50 A 50 50 0 0 1 100 50 L 100 66.6667 L 0 66.6667 Z"/></g>
  <text x="110" y="72" fill="#050505" font-size="27" font-weight="600" letter-spacing="-.8">agi labs</text>
  <text x="59" y="126" fill="#777777" font-size="15" font-weight="600" letter-spacing="2.2">BRAIN SURGERY</text>
  <text x="58" y="196" fill="#050505" font-size="48" font-weight="620" letter-spacing="-1.9"><tspan x="58" dy="0">{html.escape(line1)}</tspan><tspan x="58" dy="54">{html.escape(line2)}</tspan></text>
  <text x="55" y="420" fill="#050505" font-size="146" font-weight="650" letter-spacing="-8">{before}</text>
  <text x="244" y="411" fill="#050505" font-size="54" font-weight="560">%</text>
  <path d="M330 355h52m-18-18 19 18-19 18" fill="none" stroke="#b8b8b8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="410" y="420" fill="#154CFF" font-size="146" font-weight="650" letter-spacing="-8">{after}</text>
  <text x="599" y="411" fill="#154CFF" font-size="54" font-weight="560">%</text>
  <text x="59" y="457" fill="#777777" font-size="18">Current setup</text><text x="413" y="457" fill="#154CFF" font-size="18">Tested changes</text>
  <text x="59" y="542" fill="#555555" font-size="17" font-family="SFMono-Regular,Consolas,monospace" letter-spacing=".8">{meta}</text>
  <text x="59" y="578" fill="#888888" font-size="16">{status}</text>
  <text x="1142" y="584" fill="#aaaaaa" font-size="11" text-anchor="end" letter-spacing="1">{sample}</text>
</g>{art}</svg>'''

def breakdown_section(s: dict[str, Any]) -> str:
    rows = []
    for w in s['workflows']:
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

def report_html(s: dict[str, Any], raw: dict[str, Any] | None = None, public_source='') -> str:
    local = raw is not None; demo=s['example']; svg=social_svg(s)
    n=s['tasks']; headline, summary, status = state_copy(s)
    percent=lambda k:'&middot;' if s[k] is None else f'{s[k]}<small>%</small>'
    findings=''.join(f'<article class="finding"><div class="finding-num">0{i+1}</div><h3>{FINDINGS[x][0]}</h3><p>{FINDINGS[x][1]}</p></article>' for i,x in enumerate(s['finding_codes']))
    location=icon('lock' if local else 'globe')+('Local scan · not shared' if local else ('Public preview' if demo else 'Shared scan'))
    main_action=f'<button class="btn btn-dark" data-action="share">Share my brain scan {icon("share")}</button>' if local else f'<button class="btn btn-dark" data-action="start">Scan my AI {icon("arrow")}</button>'
    secondary=f'<button class="text-link" data-action="surgery">Review surgery {icon("arrow")}</button>' if local and s['state']=='improved' else '<button class="text-link" data-action="save-image">Save scan image ↗</button>'
    counts=f'{s["before_passes"]}/{s["before_total"]} {s["unit"]} current · {s["after_passes"]}/{s["after_total"]} with tested changes' if n>=2 else 'Some inputs or valid comparisons are still missing.'
    grade={'fixed_checks':'Fixed checks','human_checklist':'Human-reviewed checklist','model_judge':'Model-judged checklist','mixed':'Fixed checks + graded requirements'}[s['evaluator_type']]
    method=f'''<div class="method-text"><p><strong>What the percentages mean.</strong> {s['before_passes']} of {s['before_total']} {s['unit']} passed with the current setup; {s['after_passes']} of {s['after_total']} passed with the frozen candidate. A pass means meeting that task’s pre-set requirements. Both versions used the same model and inputs.</p><p>{grade}. {'Distinct tasks, repeated trials per task, so one flipped run does not move the headline by a sixth.' if s['unit']=='trials' else 'Distinct tasks, one comparison per task.'} This is a diagnostic sample, not a universal AI capability score or a guarantee for future work. {s['invalid_pairs']} invalid pairs excluded. The result is locally reported, not independently reproduced by AGI Labs.</p><p><strong>What is unchanged.</strong> Testing happened in isolation. Live settings have not been edited. The result applies to the whole tested candidate.</p></div>'''
    if local:
        method += '<p class="eyebrow" style="margin-top:20px">Local evidence · excluded from sharing</p><table class="test-table"><thead><tr><th>Task</th><th>Current</th><th>Tested</th></tr></thead><tbody id="test-body"></tbody></table>'
    else:
        rows=''.join(f'<tr><td>{x["label"]}</td><td>{x["before"]}/{x["before_total"]}</td><td>{x["after"]}/{x["after_total"]}</td></tr>' for x in s['workflows'])
        method += f'<table class="test-table"><thead><tr><th>Workflow</th><th>Current</th><th>Tested</th></tr></thead><tbody>{rows}</tbody></table><p class="field-hint">Only broad categories and measurements are shared. Private task inputs, skill contents, and logs are not included.</p>'
    dialogs=modal('evidence-dialog','The numbers, explained.','Measured on the tested tasks. Not a claim about maximum AI potential.',method)
    dialogs+=modal('start-dialog','Scan your AI.','Start inside your coding agent, not in a new app.',f'''<div class="method-text"><p>Use the Brain Surgery skill with your existing setup. It inspects permitted recent work, tests a bounded candidate, then opens this report.</p></div><div class="plan-code">Run Brain Surgery. Scan my approved recent tasks and installed skills. Test changes in isolation. Do not apply or upload anything.</div><div class="modal-actions"><button class="btn btn-dark" data-action="copy-start">Copy scan request {icon('arrow')}</button></div>''')
    if local:
        share=f'''<div class="card-frame"><img data-social alt="Exact Brain Surgery social card preview."/></div><div class="preview-note"><span>This is exactly what people will see.</span><button class="text-link" data-action="public-preview">Preview page ↗</button></div><p class="privacy-line">{icon('lock')}<span>Only this summary leaves your device. No chats, files, private skill names, prompts, or outputs.</span></p><div class="modal-actions"><button class="btn btn-outline" data-action="save-image">Save image</button><button class="btn btn-dark" data-action="publish-preview">Create share link {icon('arrow')}</button></div><p class="modal-fine">{'Prototype: publishing is not connected.' if demo else 'Publishing must use the approved AGI Labs report service.'}</p>'''
        dialogs+=modal('share-dialog','Share the scan. Not the work.','No account. No profile. No extra setup.',share)
        published=f'''<div class="published-panel"><h3>Public view ready.</h3><p>This prototype has not uploaded anything or created a hosted URL.</p></div><div class="modal-actions"><button class="btn btn-dark" data-action="public-preview">Open public preview {icon('arrow')}</button><button class="btn btn-outline" data-action="save-image">Save image</button></div><div class="caption" id="share-caption"></div><div class="preview-note"><button class="text-link" data-action="copy-caption">Copy caption</button><button class="text-link" data-action="export-public">Export public HTML ↗</button></div><details class="disclosure"><summary>Inspect what would be shared</summary><div class="inside">Only the allowlisted summary is required to host a report.<br><button class="text-link" data-action="export-summary">Export summary JSON ↗</button></div></details>'''
        dialogs+=modal('published-dialog','Ready to share.','Same report. Private work stays local.',published)
        items=''.join(f'<div class="plan-item"><strong>{html.escape(p["title"])}</strong><p>{html.escape(p["description"])}</p><div class="plan-code">{html.escape(p["patch_preview"])}</div></div>' for p in raw.get('plan',{}).get('changes',[]))
        body=f'''<div class="method-text"><p>The scan tested these changes together. Your live setup is unchanged. Review the exact diff with your agent before approving surgery.</p></div><div class="plan">{items}</div><div class="modal-actions"><button class="btn btn-dark" data-action="export-plan">Export surgery plan {icon('arrow')}</button></div><p class="modal-fine">Exporting does not apply anything. The runner must verify the original configuration and create rollback material before writing.</p>'''
        dialogs+=modal('surgery-dialog','Surgery needs approval.','Tested together. Not applied.',body)
    badge='<div class="demo">DESIGN PREVIEW · ILLUSTRATIVE RESULTS · NO AUDIT OR UPLOAD</div>' if demo else ''
    js=(ASSETS/'report.js').read_text(); css=(ASSETS/'report.css').read_text()
    brain=brain_svg(100*s['before_passes']/s['before_total'] if s['before_percent'] is not None else None,100*s['after_passes']/s['after_total'] if s['after_percent'] is not None else None,prefix='report-brain')
    before_css=s['before_percent'] if s['before_percent'] is not None else 0
    after_css=s['after_percent'] if s['after_percent'] is not None else 0
    local_payload={k:raw[k] for k in ('pairs','plan') if k in raw} if raw else None
    source_script=f'<script id="public-source" type="text/plain">{b64(public_source)}</script>' if local else ''
    local_script=f'<script id="local-data" type="application/json">{safejson(local_payload)}</script>' if local else ''
    metadata=f'<meta property="og:type" content="website"><meta property="og:title" content="Brain Surgery by AGI Labs &middot; {html.escape(headline)}"><meta property="og:description" content="{n} tested tasks. Current versus tested setup. Tested, not applied.{" Design example." if demo else ""}"><meta property="og:image" content="social-card.svg"><meta name="twitter:card" content="summary_large_image">' if not local else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer"><title>Brain Surgery by AGI Labs &middot; {'local scan' if local else 'shared scan'}</title><meta name="description" content="Measure which skills actually improve your work, and whether your agent reaches them.">{metadata}<style>{css}</style></head><body>{badge}<div class="wrap"><nav class="nav" aria-label="Report header"><a class="brand" href="/" aria-label="AGI Labs home" rel="noreferrer">{MARK}agi labs</a><span class="location">{location}</span></nav><main><header class="head"><div><h1>Brain Surgery.</h1><p>{s['skills_inspected']} skills inspected · same model</p></div><span class="status">{status}</span></header><section class="hero" style="--before:{before_css}%;--after:{after_css}%" aria-label="Test pass rate comparison"><div class="eyebrow"><span class="cross"></span>Brain scan complete</div><h2>{headline}</h2><div class="score-row"><div><div class="score score-before">{percent('before_percent')}</div><div class="score-label">Current setup</div></div><div class="score-arrow" aria-hidden="true">→</div><div><div class="score score-after">{percent('after_percent')}</div><div class="score-label">Tested changes</div></div></div><div class="hero-art">{brain}</div><div class="hero-bottom"><strong>{n} tasks · {s['workflow_count']} workflows · test pass rate</strong><span>Tested changes are still unapplied.</span></div></section><section class="summary"><div><strong>{summary}</strong><p>{counts}</p></div><button class="text-link" data-action="evidence">{'View tests' if local else 'About these numbers'} {icon('arrow')}</button></section><section class="actions"><div class="action-left">{main_action}<p class="action-note">{'Share first. Surgery can wait.' if local else 'Run the same audit on your own work.'}</p></div>{secondary}</section>{breakdown_section(s)}<section class="findings" aria-label="Scan findings">{findings}</section></main><footer class="footer"><span>Brain Surgery, by AGI Labs.<br>{'Private until you choose to share.' if local else 'Shared measurements. Private work stays private.'}</span><button class="text-link" data-action="evidence">How the test works ↗</button></footer></div>{dialogs}<div id="toast" class="toast" role="status" aria-live="polite"></div><script id="summary-data" type="application/json">{safejson(s)}</script>{local_script}<script id="social-source" type="text/plain">{b64(svg)}</script>{source_script}<script>{js}</script></body></html>'''

def render(raw: dict[str,Any], out: Path) -> dict[str,Any]:
    out.mkdir(parents=True,exist_ok=True,mode=0o700); s=summarize(raw)
    public=report_html(s)
    (out/'public-report.html').write_text(public)
    (out/'local-report.html').write_text(report_html(s,raw,public))
    (out/'social-card.svg').write_text(social_svg(s))
    (out/'public-summary.json').write_text(json.dumps(s,indent=2))
    for name in ('public-report.html','local-report.html','social-card.svg','public-summary.json'):
        os.chmod(out/name,0o600)
    return s

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input',required=True,type=Path); p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    try: raw=json.loads(a.input.read_text()); s=render(raw,a.out)
    except (OSError,ValueError,TypeError,KeyError) as e: p.exit(2,f'Render failed: {e}\n')
    print(f'Created local/public HTML and social SVG. State: {s["state"]}. No upload or live setup changes.')
if __name__=='__main__': main()
