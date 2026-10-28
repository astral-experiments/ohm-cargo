#!/usr/bin/env python3
"""Reproduce a paired post-edit Ohm benchmark on an x86-64 Linux host."""
import argparse
import contextlib
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import time

UV = 'c22e6b71933443e9cd299d4b6ac8de035ed4825b'
FILE = Path('crates/uv/src/install_source.rs')
WILD = Path('lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')
COMMANDS = {'check':['check'],'build':['build'],'test':['test','--no-run']}

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def cp(src,dst):
    subprocess.run(['cp','-a','--reflink=auto','--',src,dst],check=True)

def switch(src,dest):
    temp=dest.with_name(dest.name+'.bench-switch')
    os.link(src,temp);os.replace(temp,dest);temp.unlink(missing_ok=True)
    assert dest.samefile(src)

def changed(original,tag,shape):
    if shape=='predicate':
        old=b'component == cellar && next == formula'
        new=('{\n                component == cellar && (next == formula || next == OsStr::new('
             f'"uv-preview-{tag}"))\n            }}').encode()
    elif shape=='brew-help':
        old=b'brew update && brew upgrade uv';new=old+f' # edit {tag}'.encode()
    elif shape=='uvx-error':
        old=b'eprintln!("error: {err}");'
        new=('eprintln!("error: uvx could not launch uv ['+tag+']: {err}");').encode()
    else:
        raise ValueError(shape)
    assert original.count(old)==1
    return original.replace(old,new)

def order_test(periods,wins,losses):
    n=len(periods);positive=periods.count(1);negative=periods.count(-1);ties=periods.count(0)
    extreme=0;total=0
    for pos in range(positive+1):
        for neg in range(negative+1):
            z=n//2-pos-neg
            if 0<=z<=ties:
                allocations=math.comb(positive,pos)*math.comb(negative,neg)*math.comb(ties,z)
                total+=allocations
                if abs(2*(pos+negative-neg)-positive-negative)>=abs(wins-losses):extreme+=allocations
    return extreme/total

def summary(rows):
    savings=[];periods=[];times={'control':[],'candidate':[]}
    for a,b in zip(rows[::2],rows[1::2]):
        assert a['block']==b['block'] and a['source_sha256']==b['source_sha256']
        t={r['arm']:r['elapsed_ns']/1e9 for r in (a,b)}
        for k,v in t.items():times[k].append(v)
        savings.append(100*(1-t['candidate']/t['control']))
        diff=a['elapsed_ns']-b['elapsed_ns'];periods.append((diff>0)-(diff<0))
    n=len(savings);w=sum(x>0 for x in savings);l=sum(x<0 for x in savings)
    p=min(1,2*sum(math.comb(w+l,j) for j in range(min(w,l)+1))/2**(w+l))
    vals=sorted(savings);rank=max((k for k in range(1,n//2+1) if 2*sum(math.comb(n,j) for j in range(k))/2**n<=.05),default=0)
    return dict(blocks=n,control_median_seconds=statistics.median(times['control']),
                candidate_median_seconds=statistics.median(times['candidate']),median_saved_percent=statistics.median(savings),
                median_interval_percent=([vals[rank-1],vals[n-rank]] if rank else None),wins=w,losses=l,
                two_sided_sign_p=p,assignment_conditioned_p=order_test(periods,w,l))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['toolchain','uv-repository','work-dir','candidate-wild']:
        parser.add_argument('--'+name,type=Path,required=True)
    for name in ['control-wild','control-cargo','candidate-cargo','seed-cargo-home']:
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--command',choices=COMMANDS,default='test')
    parser.add_argument('--edit',choices=['predicate','brew-help','uvx-error'],default='predicate')
    parser.add_argument('--pairs',type=int,default=24)
    parser.add_argument('--jobs',type=int,help='By default Cargo selects its normal parallelism.')
    parser.add_argument('--cpus',help='Comma-separated physical CPU IDs or ranges, for example 0-7.')
    parser.add_argument('--seed',type=int,default=1859451)
    a=parser.parse_args()
    if a.pairs<2 or a.pairs>80 or a.pairs%2:parser.error('--pairs must be even and between 2 and 80')
    if a.jobs is not None and a.jobs<1:parser.error('--jobs must be positive')
    if a.cpus:
        ids=set()
        for r in a.cpus.split(','):
            v=r.split('-');ids.update(range(int(v[0]),int(v[-1])+1))
        if not ids<=os.sched_getaffinity(0):parser.error('requested CPU IDs are unavailable')
        os.sched_setaffinity(0,ids)
    release=a.toolchain.resolve(strict=True);repo=a.uv_repository.resolve(strict=True)
    version=subprocess.check_output([release/'bin/cargo','-Vv'],text=True)
    if '(ohm-1.99.0-18)' not in version:parser.error('expected official Ohm 1.99.0-18 for Linux x86-64')
    chosen={'control':{'cargo':a.control_cargo or release/'bin/cargo','wild':a.control_wild or release/WILD},
            'candidate':{'cargo':a.candidate_cargo or a.control_cargo or release/'bin/cargo','wild':a.candidate_wild}}
    for pair in chosen.values():
        for role,p in pair.items():pair[role]=p.resolve(strict=True)
    # Creating a new directory guarantees no existing checkout, cache, or toolchain is modified.
    work=a.work_dir.resolve();work.mkdir(mode=0o700)
    source=work/'uv';source.mkdir();tools=work/'toolchain';cp(release,tools)
    local_home=work/'cargo-home';local_home.mkdir();dest={r:tools/p for r,p in {'cargo':Path('bin/cargo'),'wild':WILD}.items()}
    for arm,pair in chosen.items():
        (work/arm).mkdir()
        for role,p in pair.items():
            shutil.copy2(p,work/arm/role)
    if a.seed_cargo_home:
        for name in ('registry','git'):
            d=a.seed_cargo_home.resolve()/name
            if d.is_dir():cp(d,local_home/name)
    with subprocess.Popen(['git','-C',repo,'archive',UV],stdout=subprocess.PIPE) as git:
        subprocess.run(['tar','-xf','-','-C',source],stdin=git.stdout,check=True)
        if git.wait():raise RuntimeError('git archive failed for pinned uv revision')
    target=work/'target'
    src=source/(Path('crates/uv/src/bin/uvx.rs') if a.edit=='uvx-error' else FILE)
    original=src.read_bytes();original_stat=src.stat();lock_before=digest(source/'Cargo.lock')
    env=dict(HOME=os.environ['HOME'],PATH=f"{tools/'bin'}:/usr/local/bin:/usr/bin:/bin",LANG='C.UTF-8',LC_ALL='C.UTF-8',TZ='UTC',
             CARGO_HOME=str(local_home),CARGO_TARGET_DIR=str(target),CARGO_TERM_COLOR='never',RUSTC=str(tools/'bin/rustc'),RUSTDOC=str(tools/'bin/rustdoc'))
    if not a.seed_cargo_home:
        subprocess.run([dest['cargo'],'fetch','--locked'],cwd=source,env=env,check=True)
    env['CARGO_NET_OFFLINE']='true'
    argv=[str(dest['cargo']),*COMMANDS[a.command]]
    if a.jobs:argv.append('-j'+str(a.jobs))
    rng=random.Random(a.seed);orders=[['control','candidate'],['candidate','control']]*(a.pairs//2);rng.shuffle(orders)
    tags=list(range(10,10+a.pairs));rng.shuffle(tags)
    manifest=dict(uv=UV,version=version,argv=argv,affinity=sorted(os.sched_getaffinity(0)),edit=a.edit,seed=a.seed,
                  inputs={k:{q:digest(p) for q,p in v.items()} for k,v in chosen.items()},cargo_lock=lock_before,
                  schedule=[{'tag':f'RE{n:02}','order':o} for n,o in zip(tags,orders)])
    (work/'plan.json').write_text(json.dumps(manifest,indent=2)+'\n')
    def run(label,strict=False):
        logfile=work/(label+'.log')
        with logfile.open('x') as log:
            start=time.perf_counter_ns()
            proc=subprocess.Popen(argv,env=env,cwd=source,stdout=log,stderr=subprocess.STDOUT)
            _,status,usage=os.wait4(proc.pid,0);stop=time.perf_counter_ns();proc.returncode=os.waitstatus_to_exitcode(status)
        if proc.returncode:raise RuntimeError(f'Cargo failed. See {logfile}')
        body=logfile.read_text(errors='replace')
        if not re.search(r'^\s*Finished ',body,re.M) or re.search(r'^\s*(Running|Updating|Downloading|Blocking) |^running \d+ tests?',body,re.M):
            raise RuntimeError(f'unexpected Cargo work in {logfile}')
        roster=re.findall(r'^\s*Executable (.+)$',body,re.M)
        if len(roster)!=(72 if a.command=='test' else 0):raise RuntimeError(f'unexpected executable roster in {logfile}')
        rebuilt=re.findall(r'^\s*(?:Checking|Compiling) (.+)$',body,re.M)
        if strict and (len(rebuilt)!=1 or not rebuilt[0].startswith('uv v0.12.0 (')):raise RuntimeError(f'expected only edited uv to rebuild in {logfile}: {rebuilt}')
        return stop-start,usage.ru_utime,usage.ru_stime,sorted(roster)
    run('warm')
    seed_dir=work/'original-target';target.rename(seed_dir)
    for arm in chosen:cp(seed_dir,work/arm/'target')
    @contextlib.contextmanager
    def use(arm):
        park=work/arm/'target';park.rename(target)
        try:
            for role,path in dest.items():switch(work/arm/role,path)
            yield
        finally:target.rename(park)
    sample=[];roster=None
    try:
        for warm in (0,1):
            src.write_bytes(changed(original,f'RE0{warm}',a.edit))
            for arm in chosen:
                with use(arm):*_,seen=run(f'admit-{arm}-{warm}',strict=bool(warm))
                if roster is None:roster=seen
                if roster!=seen:raise RuntimeError('rosters differ between paired arms')
        with (work/'pairs.csv').open('x',newline='',buffering=1) as f:
            writer=csv.DictWriter(f,fieldnames=['block','rank','arm','tag','source_sha256','elapsed_ns','user_sec','system_sec']);writer.writeheader()
            for i,tr in enumerate(manifest['schedule']):
                data=changed(original,tr['tag'],a.edit);src.write_bytes(data);h=hashlib.sha256(data).hexdigest()
                for rank,arm in enumerate(tr['order']):
                    with use(arm):ns,u,s,seen=run(f'block-{i:02}-{rank}-{arm}',strict=True)
                    if seen!=roster:raise RuntimeError('workload roster changed')
                    row=dict(block=i,rank=rank,arm=arm,tag=tr['tag'],source_sha256=h,elapsed_ns=ns,user_sec=u,system_sec=s)
                    writer.writerow(row);sample.append(row)
                print(f'completed {i+1}/{a.pairs} pairs',flush=True)
    finally:
        src.write_bytes(original);os.utime(src,ns=(original_stat.st_atime_ns,original_stat.st_mtime_ns))
        assert digest(source/'Cargo.lock')==lock_before
    result=summary(sample)
    (work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
