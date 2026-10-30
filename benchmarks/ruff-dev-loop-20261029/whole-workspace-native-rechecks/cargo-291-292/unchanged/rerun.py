#!/usr/bin/env python3
"""Run the six ordinary Ruff commands with matched Cargo binaries and one compiler in new private directories."""
import argparse
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import importlib.util

def sibling_module(name):
    path = Path(__file__).with_name(name+'.py')
    spec = importlib.util.spec_from_file_location(name, path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    return parser

collect_execs = sibling_module('trace_exec').collect_execs
classify_role = sibling_module('native_role').role

BASE='93526150df078af7dd8fc4226cdcc469539d2001'
LOCK='c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf'
TESTS=('inlay_hints::default_inlay_hints','notebook::hover_past_end_of_cell','notebook::inlay_hints_range_past_end_of_cell')
ID='ty_server/test/e2e'
TARGETS=('target','shared','cargo-home','rustup','tmp','home')
ARGS=['cargo','+ohm','test','--workspace','--no-run','--locked','--offline','-j4','--message-format=json']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,o):
    with p.open('x') as f:json.dump(o,f,sort_keys=True,indent=2);f.write('\n')
def mem():
    return int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')))*1024
def execute(args,cwd,env,out,prefix,work,free,memory):
    assert shutil.disk_usage(work).free>free and mem()>memory
    with (out/(prefix+'.stdout')).open('xb') as o,(out/(prefix+'.stderr')).open('xb') as e:
        child=subprocess.Popen(args,cwd=cwd,env=env,stdout=o,stderr=e,start_new_session=True)
        try:
            start=time.monotonic()
            while child.poll() is None:
                if shutil.disk_usage(work).free<=free or mem()<=memory or time.monotonic()-start>=4200:
                    raise RuntimeError('space, memory, or phase-duration limit reached')
                time.sleep(.4)
        except BaseException:
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:child.wait(timeout=12)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            raise
    return child.returncode
def mkdir(d):d.mkdir(mode=0o700);return d
def outarg(a):
    return a[a.index('-o')+1] if '-o' in a else None
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ruff',type=Path,required=True,help='External Git checkout containing the registered Ruff commit, used only as the clone source')
    parser.add_argument('--registry',type=Path,required=True,help='Authenticated offline Cargo registry directory containing index/ and cache/')
    parser.add_argument('--sdk',type=Path,required=True,help='Complete matching Linux Ohm compiler SDK with rustc, std, LLVM, rust-src and stock Wild')
    parser.add_argument('--control',type=Path,required=True,help='Source-built Cargo at 84af8784')
    parser.add_argument('--candidate',type=Path,required=True,help='Source-built Cargo at 98d431a9')
    parser.add_argument('--work',type=Path,required=True,help='New, nonexistent work directory, all of its parents trusted by ordinary Cargo')
    parser.add_argument('--cpus',required=True,help='Four comma-separated logical CPUs already available to this process')
    parser.add_argument('--min-free-gib',type=int,default=8,help='Stop the owned child at this free disk floor; allow 35 GiB in addition')
    parser.add_argument('--min-memory-gib',type=int,default=4,help='Stop the owned child at this MemAvailable floor; allow 8 GiB in addition')
    a=parser.parse_args();work=a.work.absolute();sdk=a.sdk.resolve(strict=True);reg=a.registry.resolve(strict=True);cpus={int(n) for n in a.cpus.split(',')}
    if os.uname().machine!='x86_64' or os.uname().sysname!='Linux' or os.geteuid()==0 or len(cpus)!=4 or not cpus<=os.sched_getaffinity(0):
        parser.error('Use a regular Linux x86_64 user account and four available CPUs')
    free=a.min_free_gib*2**30;memory=a.min_memory_gib*2**30
    if work.exists() or not work.parent.is_dir() or min(free,memory)<=0 or shutil.disk_usage(work.parent).free<=free+35*2**30 or mem()<=memory+8*2**30:
        parser.error('Use a new directory with sufficient disk space and physical memory')
    required=['git','strace','rustup','zstd'];assert all(shutil.which(n) for n in required);os.sched_setaffinity(0,cpus)
    proxy=Path(shutil.which('rustup')).absolute().parent
    mkdir(work);view=mkdir(work/'view');ss=mkdir(work/'states');cas=mkdir(work/'complete-elf-zst');src=view/'source';copy=view/'sdk'
    subprocess.run(['git','clone','--quiet','--no-checkout','--local',a.ruff.resolve(strict=True),src],check=True)
    subprocess.run(['git','--no-optional-locks','-C',src,'checkout','--quiet','--detach',BASE],check=True)
    assert sha(src/'Cargo.lock')==LOCK and subprocess.check_output(['git','-C',src,'rev-parse','HEAD^{tree}']).decode().strip()=='62d3f106c5e41f6022847f26ff8c7dc00139f7b1'
    shutil.copytree(sdk,copy,symlinks=True);binpath=copy/'bin';assert binpath.is_dir() and not binpath.is_symlink()
    wild=copy/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd';assert wild.is_file()
    roster=json.loads((Path(__file__).parent/'fifty-targets.json').read_bytes());fixed={'/'.join((r['package'],r['kind'],r['target'])) for r in roster};assert len(fixed)==50
    lock=tomllib.loads((src/'Cargo.lock').read_text());wanted={p['name']+'-'+p['version']+'.crate':p['checksum'] for p in lock['package'] if 'checksum' in p};assert len(wanted)==498
    cache={}
    for k,expected in wanted.items():
        f=next((p for p in (reg/'cache').glob('*/'+k) if p.is_file() and sha(p)==expected),None)
        if not f:raise ValueError('Missing or changed archive '+k)
        cache[k]=f
    cases={};versions={};prep={}
    for arm,program in [('K',a.control.resolve(strict=True)),('U',a.candidate.resolve(strict=True))]:
        ar=mkdir(ss/arm);out=mkdir(ar/'reports')
        for n in TARGETS:mkdir(view/n)
        (view/'rustup/toolchains').mkdir();(view/'rustup/toolchains/ohm').symlink_to(copy)
        regarm=mkdir(view/'cargo-home/registry');shutil.copytree(reg/'index',regarm/'index',symlinks=False);(regarm/'src').mkdir();(regarm/'cache').mkdir()
        for dirname in (regarm/'index').iterdir():
            if not dirname.is_dir():continue
            dest=mkdir(regarm/'cache'/dirname.name)
            for name,source in cache.items():shutil.copyfile(source,dest/name)
        assert not any((view/'target').iterdir()) and not any((view/'shared').iterdir())
        # Atomic replace on the task-owned copy. Never overwrite a target of a donor SDK symlink.
        new=binpath/'cargo.new-for-replay';assert not new.exists();shutil.copyfile(program,new);new.chmod(0o755);os.replace(new,binpath/'cargo')
        env={'HOME':str(view/'home'),'TMPDIR':str(view/'tmp'),'RUSTUP_HOME':str(view/'rustup'),'CARGO_HOME':str(view/'cargo-home'),'CARGO_TARGET_DIR':str(view/'target'),'CARGO_BUILD_BUILD_DIR':str(view/'shared'),'CARGO_NET_OFFLINE':'true','RUSTUP_AUTO_INSTALL':'0','INSTA_UPDATE':'no','LC_ALL':'C','LANG':'C','PATH':str(proxy)+':/usr/local/bin:/usr/bin:/bin'}
        for n in ('cargo','rustc'):
            p=Path(subprocess.check_output(['rustup','which','--toolchain','ohm',n],env=env,text=True).strip());assert p.samefile(binpath/n)
            assert execute([n,'+ohm','-Vv'],src,env,out,n+'-version',work,free,memory)==0
        source_commit = {'K':'84af87848a5a952ba61ae6a2cc5b22da24130200','U':'98d431a99779ccfbcfe42dfa74dd541de3a92d05'}[arm]
        if source_commit not in (out/'cargo-version.stdout').read_text():
            raise ValueError('The supplied Cargo binary must show its source commit in cargo -Vv (or build a separately source-bound replication)')
        versions[arm]={'cargo' :sha(binpath/'cargo'),'rustc':sha(binpath/'rustc'),'wild':sha(wild),'driver':{p.name:sha(p) for p in (copy/'lib').glob('librustc_driver*.so')}}
        prep[arm]={'target_inode':(view/'target').stat().st_ino,'shared_inode':(view/'shared').stat().st_ino,'empty_prior':True}
        cases[arm]={}
        for phase in ('01-empty','02-first-unchanged','03-second-unchanged'):
            d=mkdir(out/phase);tr=mkdir(d/'trace');rc=execute(['strace','-ff','-qq','-s','524288','-e','trace=execve,execveat,exit_group','-o',tr/'exec',*ARGS],src,env,d,'cargo',work,free,memory)
            assert rc==0,(arm,phase,rc);typed=[json.loads(b) for b in (d/'cargo.stdout').read_bytes().splitlines()];assert typed[-1]=={'reason':'build-finished','success':True}
            arts=[v for v in typed if v['reason']=='compiler-artifact'];assert len(arts)==619;fresh=sum(v['fresh'] for v in arts)
            if phase=='01-empty':assert not fresh
            execs,tracehash,tracecount,resumed=collect_execs(tr);full=cached=probes=0;links=[];all_counts=collections.Counter()
            for (raw,av),count in execs.items():
                ep=Path(raw);ep=ep if ep.is_absolute() else src/ep;all_counts[ep.name]+=count
                if ep.is_file() and ep.samefile(binpath/'rustc'):
                    if classify_role(av)[0]:cached+=count
                    elif '--crate-name' not in av or (any(x=='--print' or x.startswith('--print=') for x in av) and not any(x=='--emit' or x.startswith('--emit=') for x in av)):probes+=count
                    else:full+=count
                if ep.is_file() and ep.samefile(wild):
                    found=outarg(av);assert found;links.extend([Path(found)]*count)
            selected={}
            for a0 in arts:
                ma=Path(a0['manifest_path']);exe=a0['executable'];t=a0['target']
                if not exe or not ma.is_relative_to(src) or not a0['profile']['test'] or len(t['kind'])!=1:continue
                k='/'.join([tomllib.loads(ma.read_text())['package']['name'],t['kind'][0],t['name']])
                if k not in fixed:continue
                assert k not in selected;p=Path(exe);body=sha(p);zipf=cas/(body+'.zst')
                if not zipf.exists():
                    with zipf.open('xb') as f:subprocess.run(['zstd','-q','-1','-T1','-c','--',p],stdout=f,check=True)
                    dec=subprocess.Popen(['zstd','-qd','-c','--',zipf],stdout=subprocess.PIPE);got=hashlib.file_digest(dec.stdout,'sha256').hexdigest();dec.stdout.close();assert dec.wait()==0 and got==body
                q=mkdir(d/('program-'+str(len(selected)).zfill(2)));env2={**env,'CARGO_MANIFEST_DIR':str(ma.parent),'CARGO_MANIFEST_PATH':str(ma)}
                assert execute([p,'--list'],ma.parent,env2,q,'list',work,free,memory)==0
                selection=sum(q0==p or (q0.is_file() and q0.samefile(p)) for q0 in links);assert selection<=1 and (phase!='01-empty' or selection==1)
                selected[k]={'sha256':body,'bytes':p.stat().st_size,'inventory':sha(q/'list.stdout'),'count':sum(l.endswith(b': test') for l in (q/'list.stdout').read_bytes().splitlines()),'real_wild':selection}
                if k==ID:
                    assert selected[k]['count']==200 and selected[k]['inventory']=='76d24b892727ff181fdf019636ef5e928d741eb8df4f58f06dcc626d0bf67c52'
                    for ix,n in enumerate(TESTS):
                        prefix='case-'+str(ix);assert execute([p,'--exact',n],ma.parent,env2,q,prefix,work,free,memory)==0
                        text=(q/(prefix+'.stdout')).read_bytes();assert ('test '+n+' ... ok').encode() in text.splitlines() and b'199 filtered out' in text
            assert set(selected)==fixed
            row={'typed':len(arts),'fresh':fresh,'full_rustc':full,'link_only':cached,'rustc_probes':probes,'wild':len(links),'physical_execs':dict(all_counts),'selected':selected,'native_trace_sha256':tracehash,'trace_files':tracecount,'resumed':resumed,'typed_stdout':sha(d/'cargo.stdout')}
            save(d/'result.json',row);cases[arm][phase]=row;print(arm,phase,full,cached,len(links),flush=True)
        for n in TARGETS:os.rename(view/n,ar/n)
    assert versions['K']['cargo']!=versions['U']['cargo'] and all(versions['K'][n]==versions['U'][n] for n in ('rustc','wild','driver'))
    comparisons={k:{'inventories':sorted({r['selected'][k]['inventory'] for stages in cases.values() for r in stages.values()}),'saw_full_elf':sorted({r['selected'][k]['sha256'] for stages in cases.values() for r in stages.values()})} for k in fixed}
    assert all(len(v['inventories'])==1 for v in comparisons.values());save(work/'terminal.json',{'subjects':versions,'new_physical_roots':prep,'stages':cases,'per_target_comparison':comparisons})
if __name__=='__main__':main()
