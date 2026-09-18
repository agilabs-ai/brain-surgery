"""Frozen-plan validation and deterministic acceptance checks.
Checks verify narrow requirements; a valid PPTX is not necessarily a good deck.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import zipfile
from runtime_io import digest, file_digest, safe_relative, assert_inside

WORKFLOWS={'presentations','writing','coding','research','spreadsheets','design','other'}
KINDS={'exists','contains','not_contains','max_words','json_valid','pptx_structure','xlsx_structure'}


def validate_plan(plan: dict, verify_files: bool=True) -> dict:
    if not isinstance(plan,dict) or plan.get('schema_version')!='brain-surgery-plan/0.3':
        raise ValueError('Expected brain-surgery-plan/0.3')
    tasks=plan.get('tasks',[])
    if not isinstance(tasks,list) or not 1<=len(tasks)<=6:
        raise ValueError('Plan requires 1..6 distinct task pairs')
    if not isinstance(plan.get('model'),str) or not plan['model'].strip():
        raise ValueError('Set the exact same model for both arms')
    if plan.get('invocation_mode') not in {'natural','forced'}:
        raise ValueError('Specify natural or forced invocation explicitly')
    discovery=set(plan.get('discovery_task_ids',[]));seen=set()
    for task in tasks:
        tid=task.get('task_id','')
        if not isinstance(tid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',tid) or tid in seen:
            raise ValueError('Task IDs must be unique safe identifiers')
        if tid in discovery:raise ValueError('Discovery task reused as confirmation task')
        seen.add(tid)
        if task.get('workflow') not in WORKFLOWS:raise ValueError('Unknown workflow')
        if not isinstance(task.get('prompt'),str) or not task['prompt'].strip():raise ValueError('Task needs a real prompt')
        if len(task['prompt'])>18000:raise ValueError('Prompt too large; minimize the fixture')
        for f in task.get('fixtures',[]):
            if not isinstance(f,dict):raise ValueError('Fixture must be an object')
            safe_relative(f.get('destination',''))
            path=Path(f.get('source',''))
            if not path.is_absolute():raise ValueError('Fixture source must be an absolute local path')
            if verify_files:
                if path.is_symlink() or not path.is_file():raise ValueError('Fixture must be a regular non-symlink file')
                if path.stat().st_size>10*1024*1024:raise ValueError('Fixture too large for default audit')
        dests=[x['destination'] for x in task.get('fixtures',[])]
        if len(dests)!=len(set(dests)):raise ValueError('Duplicate fixture destination')
        checks=task.get('checks',[])
        if not checks or len(checks)>12:raise ValueError('Each task needs 1..12 frozen acceptance checks')
        ids=set()
        for c in checks:
            cid=c.get('id')
            if not isinstance(cid,str) or cid in ids:raise ValueError('Check IDs must be unique')
            ids.add(cid)
            if c.get('kind') not in KINDS:raise ValueError('Unsupported deterministic check')
            safe_relative(c.get('file',''))
            if c['kind'] in {'contains','not_contains'} and not isinstance(c.get('value'),str):raise ValueError('Text check requires a string value')
            if c['kind']=='max_words' and (type(c.get('value')) is not int or c['value']<0):raise ValueError('Invalid word limit')
    settings=plan.get('settings',{})
    for k in ('current','candidate','context'):
        value=settings.get(k)
        if not isinstance(value,str):raise ValueError(f'Missing settings.{k} path')
        path=Path(value)
        if not path.is_absolute():raise ValueError('Configuration snapshots must be absolute paths')
        if verify_files:
            if path.is_symlink() or not path.is_file():raise ValueError('Missing regular configuration snapshot')
            if path.stat().st_size>512*1024:raise ValueError('Configuration snapshot too large')
    budget=plan.get('budget',{})
    ranges={'max_jobs':(1,12),'max_total_tokens':(1,500000),'tokens_per_job':(1,50000),
            'seconds_per_job':(1,300),'wall_seconds':(1,1800)}
    for k,(lo,hi) in ranges.items():
        if type(budget.get(k)) is not int or not lo<=budget[k]<=hi:raise ValueError(f'Invalid budget.{k}')
    return plan


def freeze_plan(plan: dict) -> dict:
    validate_plan(plan)
    if 'seal' in plan:raise ValueError('Plan already sealed; start a new plan to change it')
    for task in plan['tasks']:
        for fixture in task.get('fixtures',[]):fixture['sha256']=file_digest(Path(fixture['source']))
    plan['settings_sha256']={k:file_digest(Path(v)) for k,v in plan['settings'].items() if k in {'current','candidate','context'}}
    plan['seal']=digest(plan)
    return plan


def verify_seal(plan: dict) -> None:
    seal=plan.get('seal');copy={k:v for k,v in plan.items() if k!='seal'}
    if not seal or digest(copy)!=seal:raise ValueError('Frozen plan changed or has no seal')
    validate_plan(plan)
    for task in plan['tasks']:
        for fixture in task.get('fixtures',[]):
            if file_digest(Path(fixture['source']))!=fixture.get('sha256'):raise ValueError('Fixture changed after plan freeze')
    for k in ('current','candidate','context'):
        if file_digest(Path(plan['settings'][k]))!=plan['settings_sha256'][k]:raise ValueError('Configuration changed after freeze')


def grade(checks: list[dict], workspace: Path) -> list[dict]:
    results=[]
    for check in checks:
        passed=False;note=''
        try:
            path=assert_inside(workspace/safe_relative(check['file']),workspace)
            if not path.is_file():note='Output file missing'
            elif path.stat().st_size>12*1024*1024:note='Output exceeds audit inspection limit'
            elif check['kind']=='exists':passed=path.stat().st_size>0;note='Nonempty file' if passed else 'Empty file'
            elif check['kind'] in {'contains','not_contains','max_words','json_valid'}:
                text=path.read_text(encoding='utf-8')
                if check['kind']=='contains':passed=check['value'] in text;note='Required text check'
                elif check['kind']=='not_contains':passed=check['value'] not in text;note='Forbidden text check'
                elif check['kind']=='max_words':
                    count=len(re.findall(r'\S+',text));passed=count<=check['value'];note=f'{count} words; limit {check["value"]}'
                else:json.loads(text);passed=True;note='Valid JSON'
            elif check['kind'] in {'pptx_structure','xlsx_structure'}:
                with zipfile.ZipFile(path) as z:
                    names=set(z.namelist())
                    part='ppt/presentation.xml' if check['kind']=='pptx_structure' else 'xl/workbook.xml'
                    passed=part in names and '[Content_Types].xml' in names
                    note='Container parts found; visual/formula quality is not measured'
            else:note='Unknown check'
        except (ValueError,OSError,UnicodeError,zipfile.BadZipFile,KeyError) as exc:
            note=f'Check failed: {type(exc).__name__}'
        results.append({'id':check['id'],'kind':check['kind'],'passed':bool(passed),'note':note})
    return results
