#!/usr/bin/env python3
"""Measure complete edited cargo +ohm check on two independently warmed Ruff workspaces."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import time

PIN = '93526150df078af7dd8fc4226cdcc469539d2001'
MARCH = '67602512b6cc90dad377b8b8709b981a6184fe37'
CHILD = '42cbce538b57961231b20fca524bbc16e857f5c3'
CASES = {'discovery':(PIN,520,35,1), 'adjacent':(MARCH,433,22,1), 'public-lexer':(PIN,520,35,35)}
HERE = Path(__file__).resolve().parent


def git(repo, *args):
    return subprocess.check_output(['git','--no-optional-locks','-C',repo,*args],text=True)


def copy(source, dest):
    subprocess.run(['cp','-a','--reflink=auto',source,dest],check=True)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('case',choices=CASES)
    p.add_argument('--before',required=True,type=Path,help='clean, linked Ruff checkout at the pinned parent')
    p.add_argument('--after',type=Path,help='real child checkout for the adjacent case')
    p.add_argument('--sysroot',required=True,type=Path,help='common compatible Ohm rustc, std and LLVM')
    p.add_argument('--cargo',required=True,type=Path,help='Ohm Cargo binary held fixed across arms')
    p.add_argument('--control',required=True,type=Path,help='complete baseline librustc_driver*.so file')
    p.add_argument('--treatment',required=True,type=Path,help='complete treatment librustc_driver*.so file')
    p.add_argument('--cargo-home',required=True,type=Path,help='private populated registry and git cache')
    p.add_argument('--state',required=True,type=Path,help='new dedicated directory on a volume with 10 GiB available')
    p.add_argument('--pairs',type=int,default=8)
    p.add_argument('--jobs',type=int,default=6)
    p.add_argument('--random-seed',help='override the initial cohort order seed, for a separately declared confirmation')
    p.add_argument('--cpus',help='optional taskset CPU list')
    a=p.parse_args(); pin,units,expected_a,expected_b=CASES[a.case]
    repo=a.before.resolve(strict=True); rt=a.sysroot.resolve(strict=True); cargo=a.cargo.resolve(strict=True)
    registry=a.cargo_home.resolve(strict=True); state=a.state.resolve(); drivers={k:v.resolve(strict=True) for k,v in [('A',a.control),('B',a.treatment)]}
    assert a.pairs>0 and not state.exists() and (repo/'.git').is_file()
    assert state!=repo and not state.is_relative_to(repo), 'state must be outside the source checkout'
    assert git(repo,'rev-parse','HEAD').strip()==pin and not git(repo,'status','--porcelain')
    assert drivers['A'].name==drivers['B'].name and (rt/'lib'/drivers['A'].name).is_file()
    state.mkdir(parents=True); mount=state/'store'; mount.mkdir(); ledger=state/'receipts'; ledger.mkdir()
    rustup=state/'rustup'; (rustup/'toolchains').mkdir(parents=True); (rustup/'toolchains/ohm').symlink_to(rt)
    (rustup/'settings.toml').write_text('version = "12"\nprofile = "minimal"\n')
    (state/'toolchains.json').write_text(json.dumps({k:digest(v) for k,v in {**drivers,'cargo':cargo,'rustc':rt/'bin/rustc'}.items()},indent=2)+'\n')
    wrapper=state/'rustc-wrapper'; wrapper.write_text('''#!/bin/sh
case " $* " in *" --crate-name "*)
    directory="$CONTROL_DRIVER"
    case "$CARGO_MANIFEST_DIR" in "$RUFF_CHECKOUT"/crates/*) directory="$SUBJECT_DRIVER";; esac
    printf '%s\\0' "$@" > "$RECEIPT/compile.$$.argv"
    printf '%s\\n' "$directory" "$CARGO_MANIFEST_DIR" > "$RECEIPT/compile.$$.driver"
    export LD_LIBRARY_PATH="$directory:$OHM_SYSROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    set -- "$@" --sysroot "$OHM_SYSROOT";;
esac
exec "$@"
'''); wrapper.chmod(0o755)
    patch=HERE/(a.case+'.patch'); paths=[line.split('\t',2)[2] for line in subprocess.check_output(['git','apply','--numstat',patch],text=True).splitlines()]
    if a.case=='adjacent':
        assert a.after is not None, 'the adjacent case requires --after'
        edited=a.after.resolve(strict=True)
        assert (edited/'.git').is_file() and git(edited,'rev-parse','HEAD').strip()==CHILD
        assert not git(edited,'status','--porcelain') and git(edited,'rev-parse','HEAD^').strip()==pin
    else:
        edited=state/'edited'; copy(repo,edited)
        args=['git','--git-dir='+git(repo,'rev-parse','--absolute-git-dir').strip(),'--work-tree='+str(edited),'apply','-R']
        subprocess.run([*args,'--check',patch],cwd=edited,check=True); subprocess.run([*args,patch],cwd=edited,check=True)
    overlays={Path('.git')} if a.case=='adjacent' else set()
    for name in paths:
        rel=Path(name)
        while not (repo/rel).exists() or not (edited/rel).exists():rel=rel.parent
        assert rel!=Path('.');overlays.add(rel)
    rustup_cargo=Path(shutil.which('cargo'))
    def invoke(arm,label,target,changed):
        receipt=ledger/label;receipt.mkdir()
        ns=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',target,mount,'--bind',registry,registry,'--bind',receipt,receipt,'--ro-bind',cargo,rt/'bin/cargo']
        if changed:
            for name in paths:
                if a.case!='adjacent' and (edited/name).is_file():os.utime(edited/name,None)
            for rel in sorted(overlays):ns+=['--ro-bind',edited/rel,repo/rel]
        args=[*(['taskset','-c',a.cpus] if a.cpus else []),*ns,'--chdir',repo,'--',rustup_cargo,'+ohm','check','--offline','--locked','--message-format=json']
        env=dict(os.environ,RUSTUP_HOME=str(rustup),RUSTUP_TOOLCHAIN='ohm',CARGO_HOME=str(registry),CARGO_TARGET_DIR=str(mount/'target'),CARGO_BUILD_BUILD_DIR=str(mount/'shared'),CARGO_BUILD_JOBS=str(a.jobs),CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',RUSTC=str(rt/'bin/rustc'),RUSTC_WRAPPER=str(wrapper),OHM_SYSROOT=str(rt),CONTROL_DRIVER=str(drivers['A'].parent),SUBJECT_DRIVER=str(drivers[arm].parent),RUFF_CHECKOUT=str(repo),RECEIPT=str(receipt),GIT_OPTIONAL_LOCKS='0',CARGO_TERM_COLOR='never',LC_ALL='C.UTF-8')
        start=time.monotonic_ns()
        with (receipt/'stdout.jsonl').open('wb') as stdout,(receipt/'stderr').open('wb') as stderr:
            rc=subprocess.run(args,env=env,stdout=stdout,stderr=stderr).returncode
        elapsed=time.monotonic_ns()-start; assert rc==0,(receipt,(receipt/'stderr').read_text()[-2500:])
        rows=[r for l in (receipt/'stdout.jsonl').read_bytes().splitlines() if (r:=json.loads(l))['reason']=='compiler-artifact']; assert len(rows)==units
        actual=[]
        for arg in receipt.glob('compile.*.argv'):
            argv=arg.read_bytes().split(b'\0'); name=argv[argv.index(b'--crate-name')+1].decode()
            if name=='___':continue
            path,manifest=arg.with_suffix('.driver').read_text().splitlines();actual.append(name)
            assert path==str(drivers[arm if manifest.startswith(str(repo)+'/crates/') else 'A'].parent)
        graph=sorted(json.dumps([r['package_id'],r['target']['name'],r['target']['kind'],r['features'],r['profile']],sort_keys=True) for r in rows)
        result={'arm':arm,'elapsed_ns':elapsed,'units':len(rows),'reported_dirty':sum(not r['fresh'] for r in rows),'rustcs':sorted(actual),'graph_sha256':hashlib.sha256('\n'.join(graph).encode()).hexdigest()}
        (receipt/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(label,elapsed/1e9,len(actual),flush=True);return result
    seeds={k:state/('seed'+k) for k in drivers}; reference=None
    for arm,seed in seeds.items():
        seed.mkdir();invoke(arm,'warm'+arm,seed,False);r=invoke(arm,'fresh'+arm,seed,False);assert not r['rustcs'];reference=reference or r['graph_sha256'];assert reference==r['graph_sha256']
    pair_order=['AB']*(a.pairs//2)+['BA']*(a.pairs//2)+(['AB'] if a.pairs%2 else [])
    seed_value=a.random_seed or 'ohm-private-trait-stage2-v1:'+('old' if a.case=='adjacent' else 'current');random.Random(seed_value).shuffle(pair_order)
    (state/'plan.json').write_text(json.dumps({'seed':seed_value,'orders':pair_order},indent=2)+'\n')
    with (state/'pairs.csv').open('w',newline='') as output:
        csvout=csv.writer(output);csvout.writerow(['pair','order','arm','native_ns','cargo_units','cargo_dirty','rustcs'])
        for i,order in enumerate(pair_order,1):
            for arm in order:
                target=state/'trial';copy(seeds[arm],target)
                try:r=invoke(arm,f'{i:02}{arm}',target,True)
                finally:shutil.rmtree(target)
                assert r['graph_sha256']==reference and r['reported_dirty']==expected_a and len(r['rustcs'])==(expected_a if arm=='A' else expected_b),r
                csvout.writerow([i,order,arm,r['elapsed_ns'],r['units'],r['reported_dirty'],len(r['rustcs'])]);output.flush()

if __name__=='__main__':main()
