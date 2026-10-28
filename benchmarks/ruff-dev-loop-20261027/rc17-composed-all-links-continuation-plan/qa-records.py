"""Run the corrected comparison against every archived native command and the true first phase."""
import collections,copy,hashlib,json,sys
from pathlib import Path
def audit(records):
 p=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
 w=p/'ruff-evaluation-v2';r=p/'whole-wild-width-v1';read=lambda f:json.loads(f.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
 phases=['seed-repeat1','seed-repeat2','selected-observer','repeat-observer','selected-composed','repeat-composed']
 targets=read(r/'targets.json');results={}
 for label in [*phases,'stopped-first']:
    phase='seed-repeat1' if label=='stopped-first' else label
    old=w/phase;lookup=r/'commands/seed-repeat1' if label=='stopped-first' else old
    disk=(lookup/'products.json').read_bytes();file=json.loads(disk);msgs=[json.loads(row) for row in (lookup/'stdout').read_bytes().splitlines()]
    memory={**file,'diagnostics':[(j['package_id'],j['message']) for j in msgs if j['reason']=='compiler-message']}
    decoded=records.check_wire(memory,disk)
    own={k for j in msgs if j['reason']=='compiler-artifact' and j['package_id'].startswith('path+') for k in [*j['filenames'],j['executable']] if k}
    registry=read(lookup/'registry-native.json') if (lookup/'registry-native.json').is_file() else {k:v for k,v in decoded['native'].items() if k not in own}
    decoded={**decoded,'native':{k:v for k,v in decoded['native'].items() if k in own}};gold=read(old/'products.json')
    records.compare(phase,decoded,gold,registry,targets)
    # Change one real channel and one real unaffected raw native input as negative controls.
    neg=copy.deepcopy(decoded);neg['fresh']+=1
    try:records.compare(phase,neg,gold,registry,targets)
    except AssertionError:pass
    else:raise AssertionError('incorrect fresh count accepted')
    neg=copy.deepcopy(decoded);absent=next(k for k in neg['native'] if k not in targets);neg['native'][absent]='0'*64
    try:records.compare(phase,neg,gold,registry,targets)
    except AssertionError:pass
    else:raise AssertionError('incorrect physical product accepted')
    wrong=copy.deepcopy(memory);wrong['diagnostics']=[]
    assert memory['diagnostics']
    try:records.check_wire(wrong,disk)
    except AssertionError:pass
    else:raise AssertionError('incorrect diagnostic accepted')
    results[label]={'sha256':sha(disk),'whole_wire_bytes':len(disk),'diagnostics':len(memory['diagnostics']),
      'native':len(decoded['native']),'registry':len(registry),'fresh':decoded['fresh'],'all_preserved_channels':True,
      'altered_fresh_raw_or_diagnostic_each_rejected':True}
 return results
if __name__=='__main__':
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 import records
 print(json.dumps(audit(records),indent=2,sort_keys=True))
