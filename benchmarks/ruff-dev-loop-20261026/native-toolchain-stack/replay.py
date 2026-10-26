"""Time native Ruff workspace checks using independently warmed complete toolchains."""
import argparse
import csv
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import time

PIN = '93526150df078af7dd8fc4226cdcc469539d2001'
ARMS = ('parent', 'candidate')
WANTED = {
    'private': ('parser-ast-discovery.patch','e98e3786c9911e16a5c515d7100bff55851c0e0b78a4acb5ed0053251080264c',(35,1)),
    'public': ('parser-ast-holdout.patch','8e26eef22165dae5bd873943c1b7d05123392d285d0754cd757d4007b49b89fa',(35,35)),
}
HASHES = {
    'parent_cargo':'211465de4b9e4589da2be06871acd9304dd3b94c849c1304f723484cb4f71dfc',
    'candidate_cargo':'3f5223265e4f51af56ecc1ef8737a2d2744b21faf6c3168a28012b9eba1ccb60',
    'parent_driver':'539e8623c70298849aa3043f35374ea3c7dc7215aac44011e64fccdc818f91a4',
    'candidate_driver':'051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518',
}
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def git(repo,*args):
    return subprocess.check_output(['git','--no-optional-locks','-C',repo,*args],text=True).strip()

def save(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare','rewarm','measure'])
    for name in ['ruff','state','results','sysroot','registry','patches','parent_cargo','candidate_cargo','parent_driver','candidate_driver']:
        parser.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    a=parser.parse_args()
    repo=a.ruff.resolve(); q=a.state.resolve(); out=a.results.resolve(); rt=a.sysroot.resolve()
    sources={k:getattr(a,k).resolve(strict=True) for k in HASHES}
    assert {k:sha(p) for k,p in sources.items()}==HASHES
    assert git(repo,'rev-parse','HEAD')==PIN and not git(repo,'status','--porcelain')
    index=Path(git(repo,'rev-parse','--path-format=absolute','--git-path','index'))
    index_sha=sha(index)
    lib,=rt.joinpath('lib').glob('librustc_driver-*.so')
    tc=q/'toolchain'; cargo=tc/'bin/cargo'; driver=tc/'lib'/lib.name
    store=q/'store'; wrapper=q/'log-rustc'; home=q/'home'; rustup=q/'rustup'
    if a.phase=='prepare':
        q.mkdir(mode=0o700); out.mkdir(mode=0o700)
        store.mkdir(); home.mkdir(mode=0o700); (rustup/'toolchains').mkdir(parents=True)
        (tc/'bin').mkdir(parents=True); (tc/'lib').mkdir()
        for f in rt.iterdir():
            if f.name not in ('bin','lib'):
                (tc/f.name).symlink_to(f)
        for f in (rt/'lib').iterdir():
            if f!=lib:(tc/'lib'/f.name).symlink_to(f)
        for f in (rt/'bin').iterdir():
            if f.name in ('rustc','rustdoc'):shutil.copy2(f,tc/'bin'/f.name)
            elif f.name!='cargo':(tc/'bin'/f.name).symlink_to(f)
        (q/'subjects').mkdir()
        for key,src in sources.items():
            dst=q/'subjects'/key;shutil.copy2(src,dst);assert sha(dst)==HASHES[key]
        (rustup/'toolchains/ohm').symlink_to(tc)
        (rustup/'settings.toml').write_text('version = "12"\nprofile = "minimal"\n')
        shutil.copytree(a.registry.resolve()/'registry',home/'registry',symlinks=True)
    if a.phase in ('prepare','rewarm'):
        wrapper.write_text('#!/bin/sh\ncase " $* " in\n*" --crate-name "*) printf "%s\\0" "$@" > "$RECEIPT/compile.$$.argv";;\nesac\nexec "$@" --sysroot "$OHM_SYSROOT"\n')
        wrapper.chmod(0o755)
    overlays={}
    for case,(name,digest,_) in WANTED.items():
        patch=a.patches.resolve()/name
        assert sha(patch)==digest
        files=[Path(line.split('\t',2)[2]) for line in subprocess.check_output(['git','apply','--numstat',patch],text=True).splitlines()]
        assert all(f.parts[0]=='crates' and (repo/f).is_file() for f in files)
        overlay=q/('overlay-'+case)
        if a.phase=='prepare':
            overlay.mkdir()
            for f in files:
                (overlay/f).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/f,overlay/f)
            subprocess.run(['git','apply','--no-index','--reverse','--whitespace=nowarn',str(patch)],cwd=overlay,check=True)
        overlays[case]=[(overlay/f,repo/f) for f in files]
    proxy=shutil.which('cargo')
    assert proxy
    plan=[]
    orders={}
    labels=[]
    for case,seed in [('private',814137),('public',814138)]:
        orders[case]=[list(ARMS)]*6+[list(reversed(ARMS))]*6
        random.Random(seed).shuffle(orders[case])
        labels.extend([(case,i) for i in range(12)])
    random.Random(814139).shuffle(labels)
    for case,i in labels:
        plan.append(dict(case=case,pair=i,order=orders[case][i]))
    settings=dict(plan=plan,subjects=HASHES,index=index_sha,cpus='0-15',jobs=6,system=rt.name,
                  rustc=sha(rt/'bin/rustc'),search_path=os.environ['PATH'])
    if a.phase=='prepare':
        save(out/'plan.json',settings)
    else:
        assert settings==json.loads((out/'plan.json').read_text())
    @contextmanager
    def mounted(target):
        idle=q/'empty-store'
        assert store.is_dir() and not any(store.iterdir()) and not idle.exists()
        store.rename(idle)
        try:
            target.rename(store)
            try:yield
            finally:store.rename(target)
        finally:idle.rename(store)
    @contextmanager
    def source_edit(case):
        assert not git(repo,'status','--porcelain')
        with tempfile.TemporaryDirectory(prefix='ohm-fixture-',dir=repo.parent) as saved:
            originals=[]
            try:
                for i,(src,dst) in enumerate(overlays[case]):
                    stat=dst.stat()
                    if src.is_file():
                        original=dst.read_bytes(); replacement=src.read_bytes()
                        assert original!=replacement
                        originals.append((dst,original,None,stat))
                        dst.write_bytes(replacement)
                    else:
                        backup=Path(saved)/str(i); dst.rename(backup)
                        originals.append((dst,None,backup,stat))
                yield
            finally:
                for dst,original,backup,stat in reversed(originals):
                    if backup is None:
                        dst.write_bytes(original);os.utime(dst,ns=(stat.st_atime_ns,stat.st_mtime_ns))
                    else:
                        backup.rename(dst)
                assert sha(index)==index_sha and not git(repo,'status','--porcelain')
    def invoke(arm,target,tag,case=None,verify=False):
        r=out/tag;r.mkdir()
        for dest,suffix in [(cargo,'cargo'),(driver,'driver')]:
            subject=q/'subjects'/(arm+'_'+suffix)
            if not dest.exists() or not dest.samefile(subject):
                temp=dest.with_name(dest.name+'.next')
                if suffix=='driver':
                    # Cargo fingerprints the driver inode's ctime. Changing its hard-link
                    # count on arm switches would invalidate the just-restored checkpoint.
                    temp.symlink_to(subject)
                else:
                    os.link(subject,temp)
                temp.replace(dest)
        command=['taskset','-c','0-15',proxy,'+ohm','check','--locked','--offline']
        if verify:command.append('--message-format=json')
        env=dict(os.environ,CARGO_HOME=str(home),RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',
            OHM_SYSROOT=str(tc),LD_LIBRARY_PATH=str(tc/'lib'),RUSTC=str(tc/'bin/rustc'),RUSTC_WRAPPER=str(wrapper),RECEIPT=str(r),CARGO_TARGET_DIR=str(store/'target'),
            CARGO_BUILD_BUILD_DIR=str(store/'shared'),CARGO_BUILD_JOBS='6',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',
            CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',CARGO_TERM_COLOR='never',LC_ALL='C.UTF-8',GIT_OPTIONAL_LOCKS='0')
        for key in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_BUILD_RUSTFLAGS','RUSTC_WORKSPACE_WRAPPER']:
            env.pop(key,None)
        with mounted(target),(r/'stdout').open('wb') as stdout,(r/'stderr').open('wb') as stderr:
            start=time.monotonic_ns();rc=subprocess.run(command,env=env,cwd=repo,stdout=stdout,stderr=stderr).returncode
            ns_total=time.monotonic_ns()-start
        err=(r/'stderr').read_text()
        assert rc==0 and 'Blocking waiting' not in err,(tag,err[-4500:])
        names=[]
        for f in r.glob('compile.*.argv'):
            argv=f.read_bytes().split(b'\0');name=argv[argv.index(b'--crate-name')+1].decode()
            if name!='___': names.append(name)
        result=dict(arm=arm,case=case,native_ns=ns_total,rustcs=sorted(names))
        if verify:
            units=[j for row in (r/'stdout').read_bytes().splitlines() if (j:=json.loads(row))['reason']=='compiler-artifact']
            assert len(units)==520
            graph=sorted(json.dumps([j['package_id'],j['target']['name'],j['target']['kind'],j['features'],j['profile']],sort_keys=True) for j in units)
            result.update(graph=hashlib.sha256('\n'.join(graph).encode()).hexdigest(),fresh=sum(j['fresh'] for j in units),units=len(units))
        assert sha(index)==index_sha
        if case is None:assert not git(repo,'status','--porcelain')
        save(r/'summary.json',result)
        print(tag,round(ns_total/1e9,3),len(names),flush=True)
        return result
    if a.phase in ('prepare','rewarm'):
        ref=None
        for arm in ARMS:
            seed=q/('seed-'+arm);seed.mkdir()
            invoke(arm,seed,'warm-'+arm,verify=True)
            fresh=invoke(arm,seed,'fresh-'+arm,verify=True)
            assert not fresh['rustcs'] and fresh['fresh']==520
            ref=ref or fresh['graph'];assert fresh['graph']==ref
        proof_dirs={name:len(list((home/name).iterdir())) for name in
                    ['.ohm-registry-json-v1','.ohm-registry-json-v2','.ohm-git-index-sha1dc-v1']}
        assert min(proof_dirs.values())>0,proof_dirs
        save(out/'reference.json',dict(graph=ref,index=index_sha,proof_counts=proof_dirs))
        return
    reference=json.loads((out/'reference.json').read_text())['graph']
    rosters={}
    def edited(arm,case,tag):
        with tempfile.TemporaryDirectory(dir=q) as tmp:
            target=Path(tmp)
            subprocess.run(['cp','-a','--reflink=auto',str(q/('seed-'+arm))+'/.',target],check=True)
            with source_edit(case):
                r=invoke(arm,target,tag,case)
                check=invoke(arm,target,tag+'-verify',case,verify=True)
            assert check['fresh']==520 and not check['rustcs'] and check['graph']==reference
            assert len(r['rustcs'])==WANTED[case][2][ARMS.index(arm)],(tag,r['rustcs'])
            return r
    for case in WANTED:
        for arm in ARMS:rosters[(case,arm)]=edited(arm,case,'preflight-'+case+'-'+arm)['rustcs']
    with (out/'observations.csv').open('x',newline='') as f:
        writer=csv.writer(f);writer.writerow(['case','pair','position','arm','elapsed_ns','rustcs'])
        for block in plan:
            case=block['case'];i=block['pair']
            for pos,arm in enumerate(block['order']):
                r=edited(arm,case,f'{case}-{i:02}-{pos}-{arm}')
                assert r['rustcs']==rosters[(case,arm)]
                writer.writerow([case,i,pos,arm,r['native_ns'],len(r['rustcs'])]);f.flush()
    save(out/'validation.json',dict(graph=reference,index=index_sha,rosters={case:{arm:rosters[case,arm] for arm in ARMS} for case in WANTED}))
if __name__=='__main__':main()
