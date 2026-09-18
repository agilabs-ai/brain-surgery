#!/usr/bin/env python3
"""TEST FIXTURE ONLY. No AI inference. Do not use to claim performance gains."""
import argparse
import json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--response',type=Path,required=True);a=p.parse_args()
r=json.loads(a.request.read_text());configuration=json.loads(r['configuration']);case=int(r['prompt'].split(':')[-1])
candidate=configuration.get('fixture_candidate') is True
passes=case in ([1,2,3,4,5] if candidate else [3,5])
out=Path(r['workspace'])/'output.txt';out.write_text('FIXTURE ACCEPTED' if passes else 'FIXTURE FAILED')
a.response.write_text(json.dumps({'protocol':'brain-surgery-adapter/0.3','model':r['model'],'status':'ok',
    'usage':{'total_tokens':0},'invocation':{'complete':True,'target_loaded':candidate if case<=2 else case in [3,4]},'fixture_only':True}))
