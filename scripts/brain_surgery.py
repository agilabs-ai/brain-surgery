#!/usr/bin/env python3
"""Brain Surgery local tools: inspect, freeze, compare, render, demo.
Python 3.10+. The real agent backend is a trusted explicit adapter, not a web app.
No command uploads or edits the live agent configuration.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
from evidence import freeze_plan, validate_plan
from runtime_io import load_json, write_json
ROOT=Path(__file__).resolve().parent.parent


def demo(out: Path):
    if out.exists() and any(out.iterdir()):raise ValueError('Use a new demo output directory')
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    settings=out/'fixture-settings';settings.mkdir(mode=0o700)
    write_json(settings/'current.json',{'fixture_candidate':False})
    write_json(settings/'candidate.json',{'fixture_candidate':True})
    (settings/'context.txt').write_text('Synthetic fixture. No customer data. No AI model calls.')
    tasks=[]
    for i,w in enumerate(['presentations','presentations','writing','writing','coding','coding'],1):
        tasks.append({'task_id':f't{i:02}','title':f'Synthetic task {i}','workflow':w,'prompt':f'FIXTURE CASE:{i}',
            'fixtures':[],'invocation_eligible':i<=4,'checks':[{'id':'fixture-acceptance','kind':'contains','file':'output.txt','value':'FIXTURE ACCEPTED'}]})
    plan={'schema_version':'brain-surgery-plan/0.3','example':True,'model':'fixture-no-model','model_family':'Not shared',
        'skills_inspected':18,'invocation_mode':'natural','discovery_task_ids':[],
        'settings':{'current':str((settings/'current.json').resolve()),'candidate':str((settings/'candidate.json').resolve()),'context':str((settings/'context.txt').resolve())},
        'tasks':tasks,'finding_codes':['invocation','conflict','keep'],'changes':[
            {'title':'Fixture: make invocation explicit','description':'Synthetic candidate for the package smoke test. Not a recommendation for your setup.','patch_preview':'FIXTURE_ONLY: enable fixture_candidate'}],
        'budget':{'max_jobs':12,'max_total_tokens':12000,'tokens_per_job':1000,'seconds_per_job':10,'wall_seconds':120}}
    write_json(out/'plan.frozen.json',freeze_plan(plan))
    config={'protocol':'brain-surgery-adapter/0.3','fixture_only':True,'command':[sys.executable,str(ROOT/'adapters/fixture_adapter.py')],'pass_env':[]}
    write_json(out/'adapter.json',config)
    from run_compare import compare
    from render_report import render
    result=compare(load_json(out/'plan.frozen.json'),config,out/'audit');render(result,out/'report')
    return {'report':str(out/'report/local-report.html'),'demo':True,'actual_model_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    # Delegate detailed options to each narrow executable.
    for key in ('inspect','compare','render'):
        subs.add_parser(key,add_help=False,help=f'Run {key}; add --help for its own options')
    f=subs.add_parser('freeze',help='Validate fixtures and seal the candidate/criteria before testing')
    f.add_argument('--input',type=Path,required=True);f.add_argument('--out',type=Path,required=True)
    d=subs.add_parser('demo',help='Run synthetic integration fixtures and produce report HTML; zero model calls')
    d.add_argument('--out',type=Path,required=True)
    argv=sys.argv[1:]
    delegation={'inspect':'inspect_setup.py','compare':'run_compare.py','render':'render_report.py'}
    if argv and argv[0] in delegation:
        code=subprocess.call([sys.executable,str(ROOT/'scripts'/delegation[argv[0]])]+argv[1:])
        raise SystemExit(code)
    args=parser.parse_args(argv)
    try:
        if args.command=='freeze':
            plan=freeze_plan(load_json(args.input));write_json(args.out,plan);result={'sealed_plan':str(args.out),'seal':plan['seal'],'executed':False}
        elif args.command=='demo':result=demo(args.out)
        print(json.dumps(result))
    except (ValueError,OSError,KeyError,TypeError) as e:parser.exit(2,f'Stopped: {e}\n')
if __name__=='__main__':main()
