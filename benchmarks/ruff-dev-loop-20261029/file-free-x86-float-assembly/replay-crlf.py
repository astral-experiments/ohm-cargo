#!/usr/bin/env python3
"""Replay the real Ruff CRLF screen with two source-built Ohm SDKs and one Cargo binary."""
import argparse
import collections
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tomllib

HERE=Path(__file__).resolve().parent
BASE='93526150df078af7dd8fc4226cdcc469539d2001'
CARGO='84af87848a5a952ba61ae6a2cc5b22da24130200'
LOCK='c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf'
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,obj):
    with p.open('x') as f:json.dump(obj,f,sort_keys=True,indent=2);f.write('\n')
def read(p):return json.loads(p.read_bytes())
def memory():
    return int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
def sdk_entries(path):
    out={}
    for p in sorted(path.rglob('*')):
        if p.is_dir() and not p.is_symlink():continue
        if p.is_symlink():
            out[str(p.relative_to(path))]={'symlink':os.readlink(p),'resolved_sha':h(p) if p.is_file() else None}
        else:
            assert p.is_file();out[str(p.relative_to(path))]={'bytes':p.stat().st_size,'mode':p.stat().st_mode & 0o7777,'sha256':h(p)}
    return out
def copy_cache(w,registry,wanted):
    base=w/'cargo-home'/'registry';base.mkdir();(base/'cache').mkdir();(base/'src').mkdir()
    shutil.copytree(registry/'index',base/'index',symlinks=False)
    originals={}
    for name,dig in wanted.items():
        f=next((p for p in (registry/'cache').glob('*/'+name) if p.is_file() and h(p)==dig),None)
        if not f:raise ValueError('missing or corrupt locked crate '+name)
        originals[name]=f
    # Cargo supports one logical cache per registry. Keep the original selected registry name.
    ids={f.parent.name for f in originals.values()}
    if len(ids)!=1:raise ValueError('supply one complete authenticated Cargo registry cache')
    name=ids.pop();cache=base/'cache'/name;cache.mkdir()
    for n,f in originals.items():shutil.copyfile(f,cache/n)
    assert any((base/'index').glob('*/.cache/li/bm/libm')) and len(list(cache.glob('libm-0.2.16.crate')))==1
    return name
def run():
    cli=argparse.ArgumentParser(description=__doc__)
    for opt in ('ruff','registry','control-sdk','candidate-sdk','cargo','work'):cli.add_argument('--'+opt,type=Path,required=True)
    cli.add_argument('--cpus',required=True,help='Four available CPUs, comma separated')
    cli.add_argument('--pairs',choices=(1,8),type=int,default=1,help='One independent replication pair, or the full fixed balanced order')
    cli.add_argument('--min-free-gib',type=int,default=8);cli.add_argument('--min-memory-gib',type=int,default=4)
    a=cli.parse_args();root=a.work.absolute();ruff=a.ruff.resolve(strict=True);registry=a.registry.resolve(strict=True);cpus={int(s) for s in a.cpus.split(',')};floor=a.min_free_gib*2**30;memfloor=a.min_memory_gib*2**30
    if os.geteuid()==0 or (os.uname().sysname,os.uname().machine)!=('Linux','x86_64') or len(cpus)!=4 or not cpus<=os.sched_getaffinity(0) or root.exists() or not root.parent.is_dir() or min(floor,memfloor)<=0:
        cli.error('use an ordinary Linux x86-64 account, four allowed CPUs and a new working directory')
    budget=(4+2*a.pairs)*5*2**30
    if shutil.disk_usage(root.parent).free<=floor+budget or memory()<=memfloor+8*2**30:
        cli.error(f'retain all generated states; allow {budget//2**30} GiB above the disk floor and 8 GiB above the memory floor')
    for tool in ('git','rustup','strace','cc'):assert shutil.which(tool),tool
    os.sched_setaffinity(0,cpus);root.mkdir(mode=0o700);view=root/'view';view.mkdir();states=root/'states';states.mkdir();raw=root/'observations';raw.mkdir()
    source=view/'source';sdk=view/'sdk';rustup=view/'rustup';rustup.mkdir();(rustup/'toolchains').mkdir()
    subprocess.run(['git','clone','--quiet','--no-checkout','--local',ruff,source],check=True)
    subprocess.run(['git','-C',source,'checkout','--quiet','--detach',BASE],check=True)
    assert sha_tree(source)==('62d3f106c5e41f6022847f26ff8c7dc00139f7b1',LOCK)
    work_src=(source/read(HERE/'source.json')['relative']);source_hash=h(work_src)
    assert source_hash==read(HERE/'source.json')['states']['original']
    # Use the pinned Git blob from a second checkout as the read-only source oracle, so no user checkout is modified.
    donor=root/'original';subprocess.run(['git','clone','--quiet','--no-checkout','--local',ruff,donor],check=True)
    subprocess.run(['git','-C',donor,'checkout','--quiet','--detach',BASE],check=True);assert sha_tree(donor)==sha_tree(source)
    w=a.control_sdk.resolve(strict=True);f=a.candidate_sdk.resolve(strict=True);assets={key:sdk_entries(path) for key,path in [('W',w),('F',f)]}
    assert assets['W'].keys()==assets['F'].keys()
    diff=[k for k in assets['W'] if assets['W'][k]!=assets['F'][k]]
    drivers=[k for k in diff if k.startswith('lib/librustc_driver-') and k.endswith('.so')]
    if len(drivers)!=1 or any(k not in (drivers[0],'bin/cargo') for k in diff):raise ValueError('SDKs must have equal effective contents except their one rustc_driver and the subsequently replaced Cargo binary')
    driver=drivers[0]
    shutil.copytree(w,sdk,symlinks=True);assert not (sdk/'bin').is_symlink() and not (sdk/'lib').is_symlink();(rustup/'toolchains/ohm').symlink_to(sdk)
    cargo=sdk/'bin/cargo';fresh=sdk/'bin/cargo.for-replay';assert not fresh.exists();shutil.copyfile(a.cargo.resolve(strict=True),fresh);fresh.chmod(0o755);os.replace(fresh,cargo)
    wild=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd';assert wild.is_file()
    proxy=Path(shutil.which('rustup')).absolute().parent
    env={'HOME':str(Path.home()),'PATH':str(proxy)+':/usr/local/bin:/usr/bin:/bin','RUSTUP_HOME':str(rustup),'RUSTUP_AUTO_INSTALL':'0','LC_ALL':'C','LANG':'C','OHM_LOCAL_CPUS':','.join(str(i) for i in sorted(cpus)),'OHM_LOCAL_DISK_FLOOR':str(floor),'OHM_LOCAL_MEM_FLOOR':str(memfloor),'OHM_LOCAL_CARGO_SHA':h(cargo),'OHM_LOCAL_WILD_SHA':h(wild)}
    assert CARGO in subprocess.check_output(['cargo','+ohm','-Vv'],env=env,text=True)
    wanted={p['name']+'-'+p['version']+'.crate':p['checksum'] for p in tomllib.loads((source/'Cargo.lock').read_text())['package'] if p.get('source','').startswith('registry+')};assert len(wanted)==498
    order=read(HERE/'order.json')['pairs'] if a.pairs==8 else ['WF']
    write(root/'enrolled.json',{'labels':'new independently supplied builds, local source/body claims only','pairs':order,'driver_key':driver,'drivers':{k:x[driver] for k,x in assets.items()},'SDK_inventory_digest':{k:hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for k,x in assets.items()},'cargo_SHA256':h(cargo),'stock_Wild_SHA256':h(wild),'fixed_W_Rust':'ad005f99d0b51fd62b5c237bc13b31b371a1686e','fixed_F_Rust':'3fd8c55774bf1208ff9ebb8ec0eae727c1a2daf9','source':BASE})
    results={};certified={};empty={};visits=[(0,label,'clean') for label in ('W','F')]+[(i,label,'warm') for i,pair in enumerate(order,1) for label in pair]
    for i,label,phase in visits:
        if memory()<=memfloor+5*2**30 or shutil.disk_usage(root).free<=floor+5*2**30:raise RuntimeError('physical visit entry reserve')
        cur=w if label=='W' else f;new=sdk/'lib'/'new-replay-driver';assert not new.exists();shutil.copy2(cur/driver,new);os.replace(new,sdk/driver);assert h(sdk/driver)==h(cur/driver)
        tag=f'{i:02d}-{label}-{phase}';store=states/tag;store.mkdir();out=raw/tag
        for n in ('cargo-home','target','shared','tmp'):(view/n).mkdir(mode=0o700)
        copy_cache(view,registry,wanted);assert not any((view/'target').iterdir()) and not any((view/'shared').iterdir())
        with (raw/(tag+'.stdout')).open('xb') as so,(raw/(tag+'.stderr')).open('xb') as se:
            run0=subprocess.run([sys.executable,'-IB',HERE/'measure.py','--work',view,'--donor',donor,'--save',out,'--driver-sha',h(cur/driver),'--phase',phase,'--arm',label],env=env,stdout=so,stderr=se)
        write(raw/(tag+'.status.json'),{'exit':run0.returncode});assert run0.returncode==0,tag
        j=read(out/'terminal.json')['results'];assert h(work_src)==source_hash and h(donor/read(HERE/'source.json')['relative'])==source_hash
        if phase=='clean':empty[label]=j['independent-edited']['product']
        else:
            assert j['edited']['product']==empty[label] and empty['W']==empty['F']
            for s in ('original','edited'):
                reference=certified.setdefault(s,j[s]['product']);assert reference==j[s]['product']
            results[(i,label)]={'full':dict(collections.Counter(j['edited']['full'])),'cached':dict(collections.Counter(j['edited']['link_only'])),'wild':j['edited']['wild'],'receipt':h(out/'terminal.json')}
        # Retain the complete restoreable per-visit generated state. The next run uses the same canonical names.
        for n in ('cargo-home','target','shared','tmp'):os.rename(view/n,store/n)
    changes=[];pairs=[]
    for i in range(1,len(order)+1):
        wt,ft=results[i,'W'],results[i,'F'];change=sum(ft['full'].values())-sum(wt['full'].values());changes.append(change);pairs.append({'W':wt,'F':ft,'difference':change})
    report={'pairs':pairs,'order':order,'median_full_delta':statistics.median(changes),'all_same_source_ELFs_and_behavior':certified,'source_scope':'This independent local run did not execute the separate native provider protocol.','elapsed_measurement':False}
    if len(order)==8:
        chronological=[x if o=='WF' else -x for x,o in zip(changes,order)];null=[sum(n if i in idx else -n for i,n in enumerate(chronological)) for idx in itertools.combinations(range(8),4)]
        report['two_sided_balanced_count_randomization']=[sum(abs(n)>=abs(sum(changes)) for n in null),len(null)]
    write(root/'terminal.json',report);print(json.dumps({'pairs':len(pairs),'paired_full_delta':changes,'terminal':h(root/'terminal.json')},sort_keys=True))
def sha_tree(path):
    return subprocess.check_output(['git','-C',path,'rev-parse','HEAD^{tree}'],text=True).strip(),h(path/'Cargo.lock')
if __name__=='__main__':run()

