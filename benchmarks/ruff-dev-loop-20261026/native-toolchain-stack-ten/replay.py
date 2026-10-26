"""Replay 10 Cargo + 3 rustc changes from the prior independently warmed A/B native stores."""
import argparse
import collections
from contextlib import contextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'plan.json').read_text())
ROSTERS=json.loads((HERE/'previous-rosters.json').read_text())['rosters']
PATCH={'private':'parser-ast-discovery.patch','public':'parser-ast-holdout.patch'}
BASE={'A':'parent','B':'candidate','nine':'candidate'}


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def save(path,obj):path.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')


def stable(obj):return hashlib.sha256(json.dumps(obj,separators=(',',':'),sort_keys=True).encode()).hexdigest()


def git(repo,*args):return subprocess.check_output(['git','--no-optional-locks','-C',repo,*args],text=True).strip()


def compare(a,b):
    assert set(a)==set(b),('inventory identity mismatch',len(a),len(b),sorted(a.keys()^b.keys())[:8]);return sorted(k for k in a if a[k]!=b[k])


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('phase',choices=['qualify','measure']);ap.add_argument('--state',type=Path,required=True);ap.add_argument('--prior',type=Path,required=True);ap.add_argument('--ruff',type=Path,required=True);ap.add_argument('--ten-cargo',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();q=a.state.resolve(strict=True);prior=a.prior.resolve(strict=True);repo=a.ruff.resolve(strict=True);out=a.out.resolve();tc=q/'toolchain';subjects=q/'subjects';store=q/'store';home=q/'home';proxy=Path(shutil.which('cargo'));control=subjects/'parent_cargo';nine=subjects/'candidate_cargo';ten=subjects/'candidate_cargo_ten';front=tc/'bin/rustc';drv,=(tc/'lib').glob('librustc_driver-*.so');live=tc/'bin/cargo';index=Path(git(repo,'rev-parse','--path-format=absolute','--git-path','index'));ref=json.loads((prior/'data/reference.json').read_text());assert ref['graph']==PLAN['graph'] and sha(index)==PLAN['index'] and sha(front)==PLAN['frontend'];assert git(repo,'rev-parse','HEAD')==PLAN['ruff'] and not git(repo,'status','--porcelain');assert (q/'rustup/toolchains/ohm').resolve()==tc and drv.is_symlink();assert str(proxy)=='/home/dev-user/.cargo/bin/cargo' and os.environ['PATH']=='/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin';assert sha(a.ten_cargo)==PLAN['ten_cargo'] and sha(control)==PLAN['control_cargo'] and sha(nine)==PLAN['nine_cargo_unscored'];assert sha(subjects/'parent_driver')==PLAN['control_driver'] and sha(subjects/'candidate_driver')==PLAN['stack_driver'];assert not any(store.iterdir())
    if not ten.exists():shutil.copy2(a.ten_cargo,ten)
    assert sha(ten)==PLAN['ten_cargo'];leader={'A':control,'B':ten,'nine':nine};seeds={arm:q/('seed-'+root) for arm,root in BASE.items()};patches={case:prior/name for case,name in PATCH.items()};assert all(sha(p)==PLAN['input_patches'][c] for c,p in patches.items());overlay={c:[(q/('overlay-'+c)/rel,repo/rel) for rel in (line.split('\t',2)[2] for line in subprocess.check_output(['git','apply','--numstat',p],text=True).splitlines())] for c,p in patches.items()};assert all(dst.is_file() for lst in overlay.values() for _,dst in lst)
    if a.phase=='qualify':out.mkdir(mode=0o700)
    else:assert (out/'qualification.json').is_file() and not (out/'observations.csv').exists()
    def seed_manifest():
        return {k:stable([(str(f.relative_to(seeds[k])),os.readlink(f) if f.is_symlink() else (f.stat().st_size,f.stat().st_mtime_ns,sha(f))) for f in sorted(seeds[k].rglob('*')) if f.is_file() or f.is_symlink()]) for k in ['A','B']}
    def proof_counts():
        r={k:len(list((home/k).iterdir())) for k in ref['proof_counts']};assert all(r[k]>=ref['proof_counts'][k] for k in r);return r
    def select(arm):
        for dst,src in [(live,leader[arm]),(drv,subjects/(BASE[arm]+'_driver'))]:
            if dst.exists() and dst.samefile(src):continue
            tmp=dst.with_name(dst.name+'.ten_next');assert not tmp.exists() and not tmp.is_symlink()
            if dst==drv:tmp.symlink_to(src)
            else:os.link(src,tmp)
            tmp.replace(dst)
        assert live.samefile(leader[arm]) and drv.is_symlink() and drv.resolve()==subjects/(BASE[arm]+'_driver')
    @contextmanager
    def mounted(arm):
        assert store.is_dir() and not any(store.iterdir());idle=q/'ten-idle-store';assert not idle.exists();assert shutil.disk_usage(q).free>2_030_000_000
        with tempfile.TemporaryDirectory(prefix='ten-trial-',dir=q) as tmp:
            trial=Path(tmp);subprocess.run(['cp','-a','--reflink=auto',str(seeds[arm])+'/.',trial],check=True);store.rename(idle)
            try:
                trial.rename(store)
                try:yield
                finally:store.rename(trial)
            finally:idle.rename(store)
    @contextmanager
    def edited(case):
        assert not git(repo,'status','--porcelain');original=[]
        with tempfile.TemporaryDirectory(dir=repo.parent,prefix='ohm-ten-source-') as t:
            try:
                for i,(src,dst) in enumerate(overlay[case]):
                    stat=dst.stat();data=dst.read_bytes()
                    if src.is_file():
                        replacement=src.read_bytes();assert data!=replacement;original.append((dst,data,None,stat));dst.write_bytes(replacement)
                    else:
                        moved=Path(t)/str(i);dst.rename(moved);original.append((dst,data,moved,stat))
                yield
            finally:
                for dst,data,moved,stat in reversed(original):
                    if moved is None:dst.write_bytes(data);os.utime(dst,ns=(stat.st_atime_ns,stat.st_mtime_ns))
                    else:moved.rename(dst)
                    assert dst.stat().st_mtime_ns==stat.st_mtime_ns and dst.read_bytes()==data
                assert sha(index)==PLAN['index'] and not git(repo,'status','--porcelain')
    def invoke(arm,r,verify,check_threads=None,inventory=False):
        r.mkdir();cmd=['taskset','-c',PLAN['cpus'],proxy,'+ohm','check','--locked','--offline'];
        if verify:cmd.append('--message-format=json')
        env=dict(os.environ,CARGO_HOME=str(home),RUSTUP_HOME=str(q/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',OHM_SYSROOT=str(tc),LD_LIBRARY_PATH=str(tc/'lib'),RUSTC=str(front),RUSTC_WRAPPER=str(q/'log-rustc'),RECEIPT=str(r),CARGO_TARGET_DIR=str(store/'target'),CARGO_BUILD_BUILD_DIR=str(store/'shared'),CARGO_BUILD_JOBS=str(PLAN['jobs']),CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',CARGO_TERM_COLOR='never',LC_ALL='C.UTF-8',GIT_OPTIONAL_LOCKS='0');
        for k in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_BUILD_RUSTFLAGS','RUSTC_WORKSPACE_WRAPPER']:env.pop(k,None)
        with (r/'stdout').open('wb') as so,(r/'stderr').open('wb') as se:
            start=time.monotonic_ns();rc=subprocess.run(cmd,env=env,cwd=repo,stdout=so,stderr=se).returncode;elapsed=time.monotonic_ns()-start
        err=(r/'stderr').read_text();assert rc==0 and 'Blocking waiting' not in err,(r,rc,err[-2000:]);roster=[];threads={}
        for f in r.glob('compile.*.argv'):
            args=f.read_bytes().split(b'\0');name=args[args.index(b'--crate-name')+1].decode()
            if name=='___':continue
            roster.append(name)
            if check_threads is not None:
                unit=Path(args[args.index(b'--out-dir')+1].decode()).parent;paths=list((unit/'fingerprint').glob('dep-*'));assert len(paths)==1,(unit,paths);key=str(paths[0].relative_to(store));size_before=check_threads.get(key);flags=[int(x.split(b'=')[1]) for x in args if x.startswith(b'-Zthreads=')];assert any(x.startswith(b'incremental=') for x in args) and any(x.startswith(b'crates/') and x.endswith(b'.rs') for x in args) and b'--test' not in args and b'--target' not in args;expected=[8,1] if arm=='B' and size_before is not None and size_before<=16*1024 else [8];assert flags==expected,(arm,name,key,size_before,flags,expected);threads[key]={'crate':name,'prior_dep_info_bytes':size_before,'flags':flags}
        result={'ns':elapsed,'roster':sorted(roster),'threads':threads}
        if verify:
            events=[json.loads(l) for l in (r/'stdout').read_bytes().splitlines()];units=[j for j in events if j['reason']=='compiler-artifact'];diagnostics=[j['message'] for j in events if j['reason']=='compiler-message'];graph=sorted(json.dumps([j['package_id'],j['target']['name'],j['target']['kind'],j['features'],j['profile']],sort_keys=True) for j in units);result.update(units=len(units),fresh=sum(j['fresh'] for j in units),graph=hashlib.sha256('\n'.join(graph).encode()).hexdigest(),diagnostics=stable(diagnostics));assert len(units)==520 and result['graph']==PLAN['graph']
            if inventory:
                meta={};api={}
                for u in units:
                    for fn in u['filenames']:
                        f=Path(fn)
                        if f.suffix!='.rmeta':continue
                        def key(p):return re.sub(r'/v2-[0-9a-f]{16}[^/]*/','/<context>/',str(p.relative_to(store)))
                        k=key(f);v=sha(f);assert meta.get(k,v)==v;meta[k]=v
                        for side in (f.parent.parent/'fingerprint').glob('*.public-api-hash'):
                            k=key(side);v=side.read_text().strip();assert api.get(k,v)==v;api[k]=v
                assert len(meta)==442 and len(api)==435,(len(meta),len(api));result.update(metadata=meta,api=api)
        save(r/'summary.json',result);return result
    def trial(arm,case,tag,sample=False):
        select(arm);r=out/tag;r.mkdir();
        with mounted(arm):
            warm=invoke(arm,r/'restore',True);before=invoke(arm,r/'before',True,inventory=not sample);assert before['fresh']==520 and not before['roster'];dep={str(f.relative_to(store)):f.stat().st_size for f in store.rglob('dep-*') if f.parent.name=='fingerprint' and f.is_file()}
            with edited(case):
                timed=invoke(arm,r/'edited',False,check_threads=dep);after=invoke(arm,r/'after',True,inventory=not sample)
            assert timed['roster']==ROSTERS[case][BASE[arm]] and not after['roster'] and after['fresh']==520 and after['graph']==before['graph'];assert before['diagnostics']==after['diagnostics'];
        print(tag,'%.4f'%(timed['ns']/1e9),len(timed['roster']),dict(collections.Counter(v['flags'][-1] for v in timed['threads'].values())),flush=True);return warm,before,timed,after
    def executions():
        seed=seed_manifest();before_driver={k:(subjects/k).stat().st_ctime_ns for k in ['parent_driver','candidate_driver']};proof=proof_counts()
        if a.phase=='qualify':
            cases={};compare_rows={};
            for case in ['private','public']:
                cases[case]={}
                for arm in ['A','nine','B']:
                    w,b,t,z=trial(arm,case,'qualify-'+case+'-'+arm);cases[case][arm]={'warm_roster':w['roster'],'before':b,'after':z,'threads':t['threads'],'roster':t['roster']};
                A,N,B=[cases[case][k] for k in ['A','nine','B']];compare_rows[case]={}
                for lhs,rhs,x,y in [('nine','ten',N,B),('control','ten',A,B)]:
                    for stage in ['before','after']:
                        row={k:compare(x[stage][k],y[stage][k]) for k in ['metadata','api']};compare_rows[case][lhs+'_'+rhs+'_'+stage]=row
                        if lhs=='nine':assert not row['api'],(case,stage,'same-compiler API mismatch',row['api'])
                if case=='private':assert not compare(B['before']['api'],B['after']['api'])
            assert seed==seed_manifest();save(out/'qualification.json',{'seed_digests':seed,'driver_ctimes':before_driver,'proof_counts':proof,'cases':cases,'comparisons':compare_rows});return
        pre=json.loads((out/'qualification.json').read_text());assert pre['seed_digests']==seed and pre['driver_ctimes']==before_driver
        with (out/'observations.csv').open('x',newline='') as stream,(out/'verification.csv').open('x',newline='') as valid:
            wr=csv.writer(stream);wr.writerow(['case','block','order','position','arm','elapsed_ns','rustcs','one_thread','eight_threads']);vv=csv.writer(valid);vv.writerow(['case','block','position','arm','restore_compiles','before_fresh','after_fresh','graph','diagnostics','roster_hash','thread_map_hash']);
            for item in PLAN['blocks']:
                case=item['case'];block=item['block'];order=item['order']
                for position,arm in enumerate(order):
                    w,b,t,z=trial(arm,case,f'{case}-{block:02}-{position}-{arm}',sample=True);prior_case=pre['cases'][case][arm];assert w['roster']==prior_case['warm_roster'] and t['threads']==prior_case['threads'] and b['diagnostics']==prior_case['before']['diagnostics'] and z['diagnostics']==prior_case['after']['diagnostics'];ct=collections.Counter(v['flags'][-1] for v in t['threads'].values());wr.writerow([case,block,order,position,arm,t['ns'],len(t['roster']),ct[1],ct[8]]);vv.writerow([case,block,position,arm,len(w['roster']),b['fresh'],z['fresh'],z['graph'],z['diagnostics'],stable(t['roster']),stable(t['threads'])]);stream.flush();valid.flush()
        assert seed_manifest()==seed and {k:(subjects/k).stat().st_ctime_ns for k in before_driver}==before_driver and git(repo,'rev-parse','HEAD')==PLAN['ruff'] and not git(repo,'status','--porcelain');save(out/'completion.json',{'seed_digests':seed,'driver_ctimes':before_driver,'proof_counts':proof_counts(),'index':sha(index),'source':PLAN['ruff'],'expected_scored_commands':96})
    initial=next(arm for arm,src in leader.items() if live.samefile(src) and drv.resolve()==subjects/(BASE[arm]+'_driver'))
    try:executions()
    finally:select(initial)
if __name__=='__main__':main()
