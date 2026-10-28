#!/usr/bin/env python3
"""Recompute the study from its unpacked raw receipts using only the Python stdlib."""
from collections import Counter
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parent).resolve()
ROLES={'cargo':1,'rustc':6,'wild':5}
HEAD='uv-23905aefc33b1c4d'
def read(p):return json.loads(p.read_text())
def check(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def pvalues(pairs):
    rel=[1-c/b for b,c,first in pairs]
    wins=sum(x>0 for x in rel);losses=sum(x<0 for x in rel);n=wins+losses
    p=min(1,2*sum(math.comb(n,i) for i in range(min(wins,losses)+1))/2**n) if n else 1
    vals=[math.log(b/c) if base_first else math.log(c/b) for b,c,base_first in pairs]
    stat=abs(math.fsum(x if pair[2] else -x for pair,x in zip(pairs,vals)))
    rand=[abs(math.fsum(x if i in order else -x for i,x in enumerate(vals))) for order in itertools.combinations(range(8),4)]
    return dict(median=statistics.median(rel),interval=[min(rel),max(rel)],wins=wins,losses=losses,ties=8-n,sign_p=p,order_p=sum(x>=stat-1e-12 for x in rand)/len(rand))
def check_native(log,expected):
    parsed=Counter()
    for f in log.glob('exec.*'):
        for line in f.read_text().splitlines():
            if not re.search(r'= 0$',line):continue
            match=re.match(r'^execve\("([^"\\]+)",',line);check(match,f'unknown successful syscall in {f.name}')
            parsed[match[1]]+=1
    check(dict(parsed)==read(log/'native-execs.json'),'strace-derived exec histogram')
    for role,n in ROLES.items():check(parsed[expected[role]]==n,f'run escaped the {role} wrapper')
    for name in parsed:
        if Path(name).name in {'cargo','rustc','wild','wild-ld','ld.bfd','ld','ld.lld','rust-lld'}:
            check(name in set(expected.values()),'unwrapped compiler or linker')
def check_command(label,where,phase,expected_roster):
    log=where/label['receipt'];check(log.parent.parent==where,'unexpected record path')
    rec=read(log);log=log.parent;mode=label['mode']
    raw=[read(f) for f in log.glob('*.json') if re.fullmatch(r'(cargo|rustc|wild)-\d+\.json',f.name)]
    check(Counter(r['role'] for r in raw)==ROLES,'wrong raw role count')
    check(rec['source_sha256']==label['source_sha256'] and rec['mtime_ns']==int(label['mtime_ns']),'source bytes/time')
    roles=sorted([r['role'],json.dumps(r['key'])] for r in raw)
    body=(log/'cargo.log').read_text();built=sorted([a,b] for a,b in re.findall(r'^\s*(Checking|Compiling) (.+)$',body,re.M))
    emitted=sorted(re.findall(r'^\s*Executable (.+)$',body,re.M))
    check(re.search(r'^\s*Finished ',body,re.M) and not re.search(r'^\s*(?:Running|Downloading|Updating) |^running \d+ tests?',body,re.M),'Cargo completion/workload')
    check(len(emitted)==72 and any(s.startswith('tests/it/') for s in emitted) and len(built)==1 and built[0][0]=='Compiling' and built[0][1].startswith('uv v'),'compiler/test roster')
    check(dict(compiled=built,roles=roles,tests=emitted)==rec['roster']==expected_roster,'role argv, package or executable roster')
    check(all(r['argv'][0]=='--no-fork' for r in raw if r['role']=='wild'),'forked linker')
    check({Path(r['key']).name for r in raw if r['role']=='wild'}==set(rec['files']),'ELF roster')
    check(Counter(rec['role_counts'])==ROLES,'stored process roster')
    if mode=='native':
        expected={r['role']:r['executable'] for r in raw}
        expected['wrapper']=str(Path(expected['wild']).parent/'linker/ld.bfd');check_native(log,expected)
    else:
        check(len({r['pid'] for r in raw})==12,'duplicated counted PID')
    sums={k:0 for k in ROLES}
    for r in raw:
        if mode=='count':
            check(str(r['pid']) in r['threads'] and all(x>=0 for x in r['threads'].values()) and r['instructions']==sum(r['threads'].values())>0,'per-PID thread accounting')
            sums[r['role']]+=r['instructions']
        else:check('instructions' not in r,'native cell unexpectedly counted')
    check(sums==rec['totals'] and all(sums[k]==int(label[k]) for k in ROLES) and sum(sums.values())==int(label['total']),'incorrect recorded role sum')
    return rec['files']
def check_outputs(cells):
    names=set(cells[0]);check(len(names)==5 and all(set(x)==names for x in cells),'wrong linked outputs')
    variable=[]
    for name in sorted(names):
        xs=[x[name] for x in cells]
        check(len({(x['size'],x['canonical_sha256']) for x in xs})==1,'size or invariant ELF bytes differ')
        if name!=HEAD:
            check(all(x['allowed_variable_fields'] is None and x['sha256']==x['canonical_sha256'] for x in xs),'unauthorized mask')
        else:
            check(all(x['allowed_variable_fields'] in ({'rodata_entsize':0},{'rodata_entsize':8}) for x in xs),'unexpected .rodata entry size')
        if len({x['sha256'] for x in xs})>1:
            check(name==HEAD,'unexpected whole-file mismatch')
            variable.append(dict(unit=name,sha256s=sorted({x['sha256'] for x in xs}),canonical_sha256=xs[0]['canonical_sha256']))
    return variable
def verify_cohort(which,protocol):
    d=ROOT/which
    if (d/'rejected.json').is_file():
        restoration=read(d/'restored.json');check(restoration['matches_registration'] and restoration['state']==protocol['pristine'],'restoration after rejection')
        return {'state':'rejected','problem':read(d/'rejected.json')}
    check((d/'restored.json').is_file(),f'{which} incomplete')
    restored=read(d/'restored.json');check(restored['matches_registration'] and restored['state']==protocol['pristine']==read(d/'before.json'),'pristine fixture restoration')
    cfg=protocol['cohorts'][which];admission=read(d/'admission.json');roster=admission['roster'];check(admission['role_counts']==ROLES,'wrong admission')
    different={};pairs=[];n_commands=0
    for phase in ['admission','samples']:
        with (d/(phase+'.csv')).open() as f:rows=list(csv.DictReader(f))
        check(len(rows)==(4 if phase=='admission' else 16),'incomplete phase')
        ids=[1] if phase=='admission' else cfg['edits']
        for i,n in enumerate(ids):
            part=[r for r in rows if int(r['pair_index'])==i]
            cells=cfg['admission_order'] if phase=='admission' else ['count/'+('base' if x=='A' else 'candidate') for x in cfg['orders'][i]]
            check([r['mode']+'/'+r['arm'] for r in part]==cells,'wrong preregistered order')
            check([int(r['position']) for r in part]==list(range(len(cells))) and all(r['cohort']==which and r['phase']==phase and int(r['literal_id'])==n and r['source_sha256']==cfg['edits_sha256'][str(n)] for r in part),'wrong cells or registered edit')
            check(len({r['mtime_ns'] for r in part})==1,'mtime changed within pair')
            got=[check_command(r,d,phase,roster) for r in part];v=check_outputs(got)
            if v:different[phase+'/'+str(n)]=v
            if phase=='samples':
                totals={r['arm']:int(r['total']) for r in part};pairs.append((totals['base'],totals['candidate'],part[0]['arm']=='base'));n_commands+=2
    check(sum(first for b,c,first in pairs)==4 and len(pairs)==8,'not eight balanced pairs')
    s=pvalues(pairs);ok=s['median']>0 and s['sign_p']<.05 and s['order_p']<.05
    stored=read(d/'summary.json');check(abs(stored['median_saving']-s['median'])<1e-12 and abs(stored['two_sided_sign_p']-s['sign_p'])<1e-12 and abs(stored['balanced_order_randomization_p']-s['order_p'])<1e-12 and (stored['state']=='qualified')==ok,'published result does not recompute')
    return {'state':'qualified' if ok else 'inconclusive','n_pairs':len(pairs),'counted_sample_commands':n_commands,'n_role_processes_in_samples':12*n_commands,**s,'registered_variant_groups':different,'restored':True}
def main():
    p=read(ROOT/'plan.json')
    check(sha(ROOT/'plan.json')==(ROOT/'registered.sha256').read_text().split()[0],'registration digest')
    for name,h in p['code_sha256'].items():check(sha(ROOT/name)==h,'registered code changed')
    v=read(ROOT/'calibration/PASS.json')
    for role,mult in [('cargo',1),('rustc',1),('wild',2)]:
        check(abs(v['count-high'][role]-v['count-low'][role]-1600000*mult)<=4096 and abs(v['count-outside'][role]-v['count-low'][role])<=4096,'calibration failed')
    cohorts={k:verify_cohort(k,p) for k in ['initial','replica'] if (ROOT/k).is_dir()}
    return {'cohorts':cohorts,'joint_qualification':len(cohorts)==2 and all(v['state']=='qualified' for v in cohorts.values())}
if __name__=='__main__':print(json.dumps(main(),indent=2))
