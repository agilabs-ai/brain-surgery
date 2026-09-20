"""Execute a frozen comparison through ONE explicitly configured trusted adapter.
The adapter supplies the model/agent runtime and its real OS/provider sandbox.
This coordinator provides pair isolation, grading, ordering, output limits,
local logs, job/time ceilings, and usage accounting. It is NOT a sandbox.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import tempfile
import time
from evidence import verify_seal, grade
from runtime_io import load_json, write_json, file_digest, digest, safe_relative


def invoke(command: list[str], request: Path, response: Path, timeout: float, env: dict) -> tuple[int,str]:
    """Trusted command from adapter config, never from a user transcript."""
    args=command+['--request',str(request),'--response',str(response)]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        proc=subprocess.Popen(args,stdout=stdout,stderr=stderr,env=env,start_new_session=(os.name=='posix'))
        try:rc=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name=='posix':os.killpg(proc.pid,signal.SIGKILL)
            else:proc.kill()
            proc.wait();return -9,'adapter_timeout'
        # Do not put stdout or private exception text into public summaries.
        stderr.seek(0);err=stderr.read(1200).decode('utf-8',errors='replace')
        return rc,err


def compare(plan: dict, config: dict, out: Path) -> dict:
    verify_seal(plan)
    if config.get('protocol')!='brain-surgery-adapter/0.3':raise ValueError('Unsupported adapter protocol')
    command=config.get('command',[])
    if not isinstance(command,list) or not command or not all(isinstance(x,str) and x for x in command):raise ValueError('Adapter command must be argv strings, not a shell command')
    if not config.get('fixture_only') and not config.get('sandbox_reviewed'):
        raise ValueError('Real candidate execution requires a reviewed host sandbox; a temp folder is insufficient')
    # The reviewed adapter is privileged trusted code. Minimal environment limits accidental credential inheritance;
    # it does not isolate filesystem/network access. The adapter's sandbox must do that.
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','TMPDIR','TEMP','LANG','LC_ALL') if k in os.environ}
    for name in config.get('pass_env',[]):
        if not isinstance(name,str):raise ValueError('Environment allowlist must contain names')
        if name in os.environ:env[name]=os.environ[name]
    if out.exists() and any(out.iterdir()):raise ValueError('Use a new output directory; never overwrite an earlier audit')
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    budget=plan['budget'];start=time.monotonic();used=0;jobs=0;stop=None;rows=[];ledger=[];fixture_seen=bool(config.get('fixture_only'))
    rng=random.Random(plan['seal']);context=Path(plan['settings']['context']).read_text(encoding='utf-8')
    for task in plan['tasks']:
        pair={'task_id':task['task_id'],'workflow':task['workflow'],'title':task.get('title',task['task_id']),
              'valid':False,'local_reference':task.get('source_reference',''),
              'invocation':{'eligible':bool(task.get('invocation_eligible',False)),'before':None,'after':None}}
        arms=['current','candidate'];rng.shuffle(arms);arm_results={};invalid=[]
        for arm in arms:
            remaining=budget['wall_seconds']-(time.monotonic()-start)
            if stop or jobs>=budget['max_jobs'] or remaining<=0 or used+budget['tokens_per_job']>budget['max_total_tokens']:
                stop=stop or 'budget_exhausted';invalid.append(stop);break
            verify_seal(plan)  # Refuse changing fixtures/configuration during a run.
            base=out/'runs'/task['task_id']/arm;base.mkdir(parents=True,mode=0o700)
            workspace=base/'workspace';workspace.mkdir(mode=0o700)
            for f in task.get('fixtures',[]):
                dest=workspace/safe_relative(f['destination']);dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(f['source'],dest)
            request={'protocol':'brain-surgery-adapter/0.3','plan_seal':plan['seal'],
                'model':plan['model'],'prompt':task['prompt'],'context':context,
                'configuration':Path(plan['settings'][arm]).read_text(encoding='utf-8'),
                'workspace':str(workspace.resolve()),'invocation_mode':plan['invocation_mode'],
                'limits':{'max_total_tokens':budget['tokens_per_job'],'seconds':min(remaining,budget['seconds_per_job'])},
                'instructions':'Fresh session. Restrict execution to the reviewed sandbox. Do not access the live workspace or read evaluation criteria. No external actions. Return usage and observable invocation evidence.'}
            # Do not send the expected checks, original source paths or named arm to the generation adapter.
            req=base/'request.json';res=base/'response.json';write_json(req,request)
            reserved=budget['tokens_per_job'];jobs+=1;used+=reserved
            rc,stderr=invoke(command,req,res,min(remaining,budget['seconds_per_job']),env)
            entry={'task_id':task['task_id'],'arm':arm,'exit_code':rc,'reserved_tokens':reserved,'stderr_local':stderr}
            if rc==-9:
                # Budget-caused task timeout is a failure, not an excluded sample. Unknown usage retains full reservation.
                arm_results[arm]={'passed':False,'checks':[],'error':'task_timeout','invoked':None}
            elif rc!=0 or not res.exists():
                invalid.append('adapter_infrastructure_error');stop='adapter_infrastructure_error'
            else:
                try:
                    response=load_json(res,limit=1048576)
                    fixture_seen=fixture_seen or response.get('fixture_only') is True
                    if response.get('protocol')!='brain-surgery-adapter/0.3' or response.get('model')!=plan['model']:
                        raise ValueError('Response/model mismatch')
                    if response.get('status') not in {'ok','task_failed','infrastructure_error'}:raise ValueError('Unknown response status')
                    total=response.get('usage',{}).get('total_tokens')
                    if response['status']=='infrastructure_error':
                        # A timeout/outage can make provider usage unknowable. Retain
                        # the full reservation in that case instead of relabelling a
                        # declared infrastructure failure as a malformed response.
                        if total is not None and (type(total) is not int or total<0):
                            raise ValueError('Invalid token accounting')
                        if type(total) is int:
                            used+=total-reserved;entry['reported_tokens']=total
                            if total>reserved:stop='adapter_exceeded_token_reservation'
                        invalid.append('declared_infrastructure_error');stop='adapter_infrastructure_error'
                    else:
                        if type(total) is not int or total<0:raise ValueError('Missing or invalid token accounting')
                        used+=total-reserved;entry['reported_tokens']=total
                        if total>reserved:stop='adapter_exceeded_token_reservation'
                        checks=grade(task['checks'],workspace)
                        passed=response['status']=='ok' and bool(checks) and all(c['passed'] for c in checks)
                        invoked=response.get('invocation',{}).get('target_loaded')
                        # An unsupported/incomplete invocation trace must not become a zero.
                        if type(invoked) is not bool or response.get('invocation',{}).get('complete') is not True:invoked=None
                        arm_results[arm]={'passed':passed,'checks':checks,'invoked':invoked,'status':response['status']}
                except (ValueError,OSError,TypeError) as exc:
                    invalid.append('invalid_adapter_response');stop='invalid_adapter_response';entry['error_type']=type(exc).__name__
            ledger.append(entry);write_json(out/'ledger.json',{'jobs':ledger,'used_or_reserved_tokens':used,'stop_reason':stop})
        if len(arm_results)==2 and not invalid:
            pair.update(valid=True,before=arm_results['current']['passed'],after=arm_results['candidate']['passed'],
                checks={'before':arm_results['current']['checks'],'after':arm_results['candidate']['checks']})
            if plan['invocation_mode']=='natural':
                pair['invocation'].update(before=arm_results['current']['invoked'],after=arm_results['candidate']['invoked'])
        else:pair['invalid_reason']=','.join(invalid) or 'comparison_incomplete'
        rows.append(pair)
    result={'schema_version':'brain-surgery/0.3','example':bool(plan.get('example') or fixture_seen),
        'metric_kind':'task_pass_rate','model_family':plan.get('model_family','Not shared'),'evaluator_type':'fixed_checks',
        **({'model_lift':plan['model_lift'],'stronger_model':plan.get('stronger_model')} if plan.get('model_lift') is not None else {}),
        'skills_inspected':plan.get('skills_inspected',0),'finding_codes':plan.get('finding_codes',[]),'pairs':rows,
        'plan':{'status':'draft_not_applied','candidate_bundle':plan['seal'],
            'base_configuration_fingerprint':plan['settings_sha256']['current'],'changes':plan.get('changes',[])},
        'run':{'adapter_protocol':config['protocol'],'plan_seal':plan['seal'],'jobs':jobs,'tokens_used_or_reserved':used,
            'elapsed_seconds':round(time.monotonic()-start,2),'stop_reason':stop,
            'fixture_only':fixture_seen,'invocation_mode':plan['invocation_mode']}}
    write_json(out/'result.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--approve-execution',action='store_true',help='Only after reviewing plan, cost, trusted adapter and sandbox')
    a=p.parse_args()
    if not a.approve_execution:p.error('Execution requires --approve-execution; no candidate was run')
    try:
        result=compare(load_json(a.plan),load_json(a.adapter),a.out)
        from render_report import render
        render(result,a.out/'report')
    except (ValueError,OSError,TypeError,KeyError) as e:p.exit(2,f'Comparison stopped: {e}\n')
    print(json.dumps({'result':str(a.out/'result.json'),'report':str(a.out/'report/local-report.html'),'fixture_only':result['run']['fixture_only'],'jobs':result['run']['jobs'],'stop_reason':result['run']['stop_reason'],'applied':False,'uploaded':False}))
if __name__=='__main__':main()
