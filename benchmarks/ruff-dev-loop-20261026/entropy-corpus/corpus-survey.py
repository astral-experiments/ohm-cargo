"""Record the dirty-unit fanout of complete historical patches in an isolated Ruff worktree."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

parser=argparse.ArgumentParser(description=__doc__)
for name in ('corpus','ruff','output'):
    parser.add_argument('--'+name, type=Path, required=True)
parser.add_argument('--only',nargs='*')
args=parser.parse_args()
manifest=json.loads((args.corpus/'manifest.json').read_bytes())
assert not subprocess.check_output(['git','status','--porcelain'],cwd=args.ruff)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.ruff,text=True).strip()==manifest['ruff']
assert (args.ruff/'.git').is_file()
args.output.mkdir(parents=True,exist_ok=True)
commands={'linter':'check','parser-ast':'check','formatter':'build','cli-workspace':'build','shared-library':'test','test-target':'test'}

def run(mode, label, measure=False):
    data=args.output/label
    data.mkdir(exist_ok=False)
    argv=['cargo','+ohm',mode]+(['--no-run'] if mode=='test' else [])+['--locked','--offline','--message-format=json']
    env=dict(os.environ)
    if measure: env['OHM_COUNT_OUTPUT']=str(data)
    begin=time.monotonic_ns()
    with (data/'stdout.jsonl').open('wb') as stdout,(data/'stderr').open('wb') as stderr:
        result=subprocess.run(argv,cwd=args.ruff,env=env,stdout=stdout,stderr=stderr)
    records=[]; errors=[]
    for line in (data/'stdout.jsonl').read_bytes().splitlines():
        if not line:continue
        j=json.loads(line)
        if j['reason']=='compiler-artifact':
            records.append((j['package_id'],j['target']['name'],j['target']['kind'],j['fresh']))
        if j['reason']=='compiler-message' and j['message']['level']=='error':errors.append(j['message']['message'])
    cargo_ir=None
    profiles=list(data.glob('cargo.*.ir'))
    if measure and len(profiles)==1:
        counts=[l.split() for l in profiles[0].read_text().splitlines()]
        if counts and counts[-1][0]=='P':cargo_ir=sum(int(r[3]) for r in counts if r[0]=='F')
    summary=dict(argv=argv,exit=result.returncode,wall_ns=time.monotonic_ns()-begin,total_artifacts=len(records),
                 dirty=[r[:3] for r in records if not r[-1]],cargo_instructions=cargo_ir,errors=errors)
    (data/'receipt.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(label,'exit',result.returncode,'artifacts',len(records),'dirty',len(summary['dirty']),'cargo_ir',cargo_ir,'time',round(summary['wall_ns']/1e9,2),errors[:2],flush=True)
    return summary

for edit in manifest['fixtures']:
    label=edit['label'];mode=commands[edit['stratum']]
    if edit['split']!='discovery' or (args.only and label not in args.only):continue
    patch=args.corpus/(label+'.patch');assert hashlib.sha256(patch.read_bytes()).hexdigest()==edit['patch_sha256']
    baseline=run(mode,label+'-base')
    assert baseline['exit']==0,baseline
    subprocess.run(['git','apply','--reverse','--whitespace=nowarn',str(patch)],cwd=args.ruff,check=True)
    try:
        run(mode,label+'-edit',True)
    finally:
        subprocess.run(['git','apply','--whitespace=nowarn',str(patch)],cwd=args.ruff,check=True)
        assert not subprocess.check_output(['git','status','--porcelain'],cwd=args.ruff)
