"""Validate warm, cold and standalone compiler results and retain every comparison."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

def sha(b):
    return hashlib.sha256(b).hexdigest()

def wire_equal(a,b):
    return {name:{ext:x==b[name][ext] for ext,x in af.items()} for name,af in a.items()}

def endpoint(r):
    w,c=r['warm'],r['clean']
    return dict(
        warm_cargo_exit=w['cargo_exit'], cold_cargo_exit=c['cargo_exit'],
        warm_standalone_exit=w['outside_good']['exit'],cold_standalone_exit=c['outside_good']['exit'],
        successful_processes=all(h.get('app',{}).get('exit')==0 and h['outside_good'].get('run')==0 for h in (w,c)),
        warm_intentional_error=w['outside_error']['exit'],cold_intentional_error=c['outside_error']['exit'],
        ice=any(h[k]['ice'] for h in (w,c) for k in ('outside_good','outside_error')),
        cargo_runtime=w.get('app',{}).get('out')==c['app']['out'],cargo_elf=w.get('app',{}).get('elf')==c['app']['elf'],
        standalone_runtime=w['outside_good'].get('output')==c['outside_good']['output'],
        standalone_elf=w['outside_good'].get('elf')==c['outside_good']['elf'],
        successful_diagnostics=w['outside_good']['diagnostics']==c['outside_good']['diagnostics'],
        failing_diagnostics=w['outside_error']['diagnostics']==c['outside_error']['diagnostics'],
        error_codes=sorted(d['code'] for d in c['outside_error']['diagnostics'] if d['code']),
        artifacts=wire_equal(w['artifacts'],c['artifacts']),warm_children=w['actual_children'],cold_children=c['actual_children'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--must-pass',action='store_true');a=p.parse_args()
    full={};issues=[]
    for f in sorted(a.root.glob('*/observations.json')):
        q=f.parent.name;rs=json.loads(f.read_bytes());assert len(rs)==5
        evals={r['phase']:endpoint(r) for r in rs if r['clean'] is not None}
        for phase,x in evals.items():
            warm=next(r['warm'] for r in rs if r['phase']==phase)
            expected_value=('13' if '-expn-' in q else '11') if phase=='caller' else ('9' if '-expn-' in q else '7')
            if any(lines[-1:]!=[expected_value] for lines in (warm.get('app',{}).get('out',[]),warm['outside_good'].get('output',[]))):issues.append([q,phase,'unexpected output'])
            if (x['warm_cargo_exit']!=0 or x['cold_cargo_exit']!=0 or x['warm_standalone_exit']!=0 or x['cold_standalone_exit']!=0
                or x['warm_intentional_error']!=1 or x['cold_intentional_error']!=1 or x['ice']
                or not all(x[k] for k in ('successful_processes','cargo_runtime','cargo_elf','standalone_runtime','standalone_elf','successful_diagnostics','failing_diagnostics'))
                or x['error_codes']!=['E0061','E0063']):issues.append([q,phase])
        stages={r['phase']:{'public_hash':r['warm']['leaf_public_hash']['value'],'actual_children':r['warm']['actual_children'],
                             'cargo_exit':r['warm']['cargo_exit']} for r in rs}
        # Check that a vanished expansion cannot leave the intermediate carrying a dangling identity.
        # A stable relocated expansion is the positive control for retaining the same intermediate.
        if '-expn-' in q:
            required=['facade'] if q.startswith('local') else ['facade','bundle']
            for phase in ('change','restore'):
                children=dict(stages[phase]['actual_children'])
                for name in required:
                    if ('disappears' in q and children.get(name) is not False) or ('shrink' in q and name in children):
                        issues.append([q,phase,name,'unexpected intermediate rebuild decision'])
        if any(r['warm']['cargo_exit'] for r in rs):issues.append([q,'warm_build'])
        full[q]=dict(stages=stages,endpoints=evals)
    summary={'driver':json.loads((a.root/'toolchain.json').read_bytes()),'cases':len(full),'warm_and_cold_paired_endpoints':2*len(full),'issues':issues,'by_case':full}
    (a.root/'summary.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
    print(summary['cases'],summary['warm_and_cold_paired_endpoints'],issues)
    if a.must_pass:assert not issues,issues
