"""Count genuine compilers and linkers for a new Ruff integration-test selection."""
import ast
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess as sp
import sys
import traceback

root=Path('/dev/shm/ohm-text-size-first-selection-20261028')
protocol=root/'protocol'
plan=json.loads((protocol/'plan.json').read_bytes())
src=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/source')
prior=Path('/dev/shm/ohm-published-member-h2-20261028')
sdk=prior/'installed17'
linker=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
can=root/'logical'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def save(path,obj):
    with path.open('x') as f:
        json.dump(obj,f,sort_keys=True,indent=2)
        f.write('\n')

def dig(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def git(*args):
    return sp.check_output(['git','--no-optional-locks','-C',src,*args])

def namespace(state,arm,rec):
    assert sha(root/(arm+'-cargo'))==plan['cargo'][arm]
    env=dict(PATH=str(Path(shutil.which('rustup')).parent)+':/usr/local/bin:/usr/bin:/bin',
            HOME=str(can/'home'),CARGO_HOME=str(can/'cargo'),RUSTUP_HOME=str(root/'rustup'),RUSTUP_AUTO_INSTALL='0',
            CARGO_TARGET_DIR=str(can/'target'),CARGO_BUILD_BUILD_DIR=str(can/'shared'),CARGO_NET_OFFLINE='true',
            CARGO_BUILD_JOBS='8',CARGO_TERM_COLOR='never',TMPDIR=str(can/'tmp'),LC_ALL='C.UTF-8',LANG='C.UTF-8')
    ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
        '--ro-bind',str(root),str(root),'--ro-bind',str(sdk),str(sdk),'--ro-bind',str(root/(arm+'-cargo')),str(sdk/'bin/cargo'),
        '--ro-bind',str(root/'active-range.rs'),str(src/plan['path'])]
    for name in ('target','shared','cargo','tmp','home'):
        ns+=['--bind',str(state/name),str(can/name)]
    return ns+['--bind',str(rec),str(rec),'--chdir',str(src),'--'],env

def normal(namespace,cmd,rec,name,expected=0):
    ns,env=namespace
    with (rec/(name+'.stdout')).open('xb') as so,(rec/(name+'.stderr')).open('xb') as se:
        status=sp.run([*ns,*map(str,cmd)],env=env,stdout=so,stderr=se).returncode
    save(rec/(name+'.status.json'),{'exit':status,'argv':list(map(str,cmd))})
    assert status==expected,(name,status,(rec/(name+'.stderr')).read_text(errors='replace')[-950:])

def host_path(logical,state):
    path=Path(logical)
    for name in ('target','shared'):
        if path.is_relative_to(can/name):
            return state/name/path.relative_to(can/name)
    raise ValueError(path)

def jobs(at,selected):
    matches=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[0-9a-f]+|NULL).*?\)\s+= 0$')
    rows=[]
    for f in sorted(at.glob('exec.*')):
        lines=f.read_bytes().splitlines()
        for line in lines:
            m=matches.match(line)
            if not m:
                assert not (line.startswith(b'execve(') and line.endswith(b'= 0')),f
                continue
            exe=Path(ast.literal_eval(m[1].decode()));arg=ast.literal_eval(m[2].decode())
            kind=target=None
            if exe.name=='rustc' and exe.samefile(sdk/'bin/rustc') and '--crate-name' in arg:
                target=arg[arg.index('--crate-name')+1]
                if target in ('___','__'):continue
                kind='link-only' if any(x=='link-only' or x.startswith('-Zlink-only') for x in arg) else 'full'
            elif exe.name in ('ld','ld.bfd','ld.lld','rust-lld','wild','wild-ld','mold') and '-o' in arg:
                kind='wild' if exe.samefile(linker) else 'other-linker';target=arg[arg.index('-o')+1]
            assert str(exe) not in selected,'cargo test --no-run executed a test binary'
            if kind is not None:
                mexit=re.search(rb'\+\+\+ exited with (\d+) \+\+\+',lines[-1])
                assert mexit and int(mexit[1])==0,(exe,kind)
                rows.append(dict(kind=kind,target=target,raw=hashlib.sha256(line).hexdigest(),argv=dig(arg),exit=0))
    assert not any(r['kind']=='other-linker' for r in rows)
    return rows

def run(state,arm,phase,command):
    rec=root/'receipts'/phase;rec.mkdir();(rec/'trace').mkdir()
    ns=namespace(state,arm,rec)
    trace=['strace','-ff','-q','-s','1048576','-e','trace=execve','-o',rec/'trace/exec']
    normal(ns,[*trace,*command,'--message-format=json'],rec,'cargo')
    events=[json.loads(l) for l in (rec/'cargo.stdout').read_bytes().splitlines()]
    assert events[-1]=={'reason':'build-finished','success':True}
    rows=[e for e in events if e['reason']=='compiler-artifact']
    fields=('package_id','manifest_path','target','profile','features','filenames','executable')
    typed=sorted(dig({k:x[k] for k in fields}) for x in rows)
    assert len(typed)==len(set(typed))
    native={};harness={};library=[]
    for x in rows:
        for name in x['filenames']:
            f=host_path(name,state)
            assert f.is_file(),name
            with f.open('rb') as fd: magic=fd.read(4)
            if magic==b'\x7fELF':native[name]=sha(f)
        if x['target']['name']=='ruff_text_size' and 'lib' in x['target']['kind']:
            library.extend(p for p in x['filenames'] if p.endswith('.rlib'))
        if 'test' in x['target']['kind'] and x['executable']:
            name=x['target']['name'];target=x['executable']
            assert name not in harness and target in native
            normal(ns,[target,'--list'],rec,'list-'+name)
            assert not (rec/('list-'+name+'.stderr')).read_bytes()
            listing=(rec/('list-'+name+'.stdout')).read_bytes()
            assert re.search(rb'\d+ tests?, \d+ benchmarks?\n?$',listing),listing[-100:]
            harness[name]=dict(file=target,sha256=native[target],listing=hashlib.sha256(listing).hexdigest())
    jj=jobs(rec/'trace',{x['executable'] for x in rows if x['executable']})
    counts=dict(Counter(x['kind'] for x in jj))
    diag=sorted(dig(e['message']) for e in events if e['reason']=='compiler-message')
    summary=dict(work=counts,units=len(rows),fresh=sum(bool(x['fresh']) for x in rows),roster=dig(typed),
                 diag=diag,elf=native,harness=harness,library=library)
    save(rec/'jobs.json',jj);save(rec/'products.json',summary)
    return summary

def demonstrate(state,phase,positive):
    rec=root/'receipts'/phase
    (rec/'api-probe.rs').write_text('use ruff_text_size::{TextRange,TextSize};\nfn main(){let r=TextRange::new(TextSize::new(1),TextSize::new(4));println!("{:?}",r.to_std_range());}\n')
    rlib,=read(rec/'products.json')['library'];ns=namespace(state,'B',rec)
    normal(ns,['rustc','+ohm','--edition=2024','--crate-name','api_probe',rec/'api-probe.rs','--extern','ruff_text_size='+rlib,
               '-L','dependency='+str(Path(rlib).parent),'-o',rec/'api-probe'],rec,'api-rustc',0 if positive else 1)
    if positive:
        normal(ns,[rec/'api-probe'],rec,'api-run')
        assert (rec/'api-run.stdout').read_bytes()==b'1..4\n'
    else:
        e=(rec/'api-rustc.stderr').read_bytes()
        assert b'E0599' in e and b'to_std_range' in e,e[-350:]

def main():
    assert socket.gethostname()==plan['host'] and Path(__file__).resolve()==protocol/'worker.py'
    assert git('rev-parse','HEAD').decode().strip()==plan['ruff'] and git('rev-parse','HEAD^{tree}').decode().strip()==plan['tree']
    git('diff','--quiet','HEAD','--')
    assert sha(src/plan['path'])==sha(protocol/'after-range.rs')==plan['after_sha256'] and sha(protocol/'before-range.rs')==plan['before_sha256']
    assert all(sha(f)==plan['sdk'][k] for k,f in [('rustc',sdk/'bin/rustc'),('cargo',sdk/'bin/cargo'),('wild',linker),('driver',next((sdk/'lib').glob('librustc_driver-*.so')))])
    assert shutil.disk_usage(root).free>8*2**30
    os.sched_setaffinity(0,set(plan['cpus']))
    receipt=root/'receipts';receipt.mkdir();can.mkdir()
    seed=root/'seed';seed.mkdir()
    for name in ('home','tmp','target','shared','cargo'):
        (seed/name).mkdir();(can/name).mkdir()
    (root/'rustup/toolchains').mkdir(parents=True);(root/'rustup/toolchains/ohm').symlink_to(sdk,target_is_directory=True)
    (root/'rustup/settings.toml').write_text('version = "12"\nprofile = "minimal"\n')
    sp.run(['cp','-a','--reflink=auto',prior/'state-17/cargo/registry',seed/'cargo/registry'],check=True)
    def state_view(which):
        temp=root/'next-range.rs';temp.write_bytes((protocol/(which+'-range.rs')).read_bytes());os.replace(temp,root/'active-range.rs')
    build=['cargo','+ohm','build','-p','ruff_text_size','--locked','--offline','-j8']
    state_view('before');run(seed,'B','before-build',build);demonstrate(seed,'before-build',False)
    state_view('after');run(seed,'B','after-build',build);demonstrate(seed,'after-build',True)
    base=run(seed,'B','settled-build',build)
    assert not base['work'] and base['fresh']==base['units'] and base['harness']=={}
    receipts=[]
    for i,arm in enumerate(plan['order'],1):
        assert shutil.disk_usage(root).free>5*2**30
        state=root/('state-'+str(i)+'-'+arm);sp.run(['cp','-a','--reflink=never',seed,state],check=True)
        reference=host_path(base['library'][0],seed);copied=host_path(base['library'][0],state)
        assert not copied.samefile(reference) and sha(reference)==sha(copied)
        item={}
        for step in ('first','repeat'):
            tag=f'{i}-{arm}-{step}';got=run(state,arm,tag,plan['command'])
            assert sorted(got['harness'])==plan['expected_harnesses'] and all(h['listing'] for h in got['harness'].values())
            item[step]=got
        receipts.append(dict(arm=arm,**item))
    first=receipts[0]['first'];rep=receipts[0]['repeat']
    def sig(r):return {k:r[k] for k in ('units','fresh','roster','diag','elf','harness','library')}
    guards=all(sig(r['first'])==sig(first) and sig(r['repeat'])==sig(rep) and
               all(r['first'][k]==r['repeat'][k] for k in ('harness','elf','roster','diag')) and
               not r['repeat']['work'] and r['repeat']['fresh']==r['repeat']['units'] for r in receipts)
    byarm={a:[r['first']['work'] for r in receipts if r['arm']==a] for a in 'BC'}
    actual=[]
    for i,arm in enumerate(plan['order'],1):
        jj=read(receipt/f'{i}-{arm}-first'/'jobs.json')
        crates=Counter(j['target'] for j in jj if j['kind']=='full')
        destinations=Counter(Path(j['target']).name for j in jj if j['kind']=='wild')
        actual.append(dict(arm=arm,crates=crates,destinations=destinations))
    targets=set(plan['expected_harnesses'])
    harness_link_names={Path(v['file']).name for v in first['harness'].values()}
    def repeated(rows,key,labels):
        def entries(arm):return [r[key] for r in rows if r['arm']==arm]
        b,c=entries('B'),entries('C')
        return (all(set(x)==set(y) for x in b for y in c) and all(dict(x)==dict(b[0]) for x in b) and
                all(dict(x)==dict(c[0]) for x in c) and all(c[0][t]==1 for t in labels) and
                all(b[0][t]>=c[0][t] for t in labels) and sum(b[0][t]-c[0][t] for t in labels)>=2 and
                all(b[0][t]==c[0][t] for t in set(b[0])-labels))
    fewer=all(min(b.get(k,0) for b in byarm['B'])-max(c.get(k,0) for c in byarm['C'])>=2 for k in ('full','wild'))
    fewer=fewer and repeated(actual,'crates',targets) and repeated(actual,'destinations',harness_link_names)
    save(root/'outcome.json',dict(ordinary=byarm,all_native_and_roster_guards=guards,flow_cutoff=fewer,
                                  admitted=guards and fewer,first=first['work'],units=first['units'],harnesses=sorted(first['harness']),
                                  actual_declared_elf=len(first['elf']),by_target=actual,test_bodies_run=0,timing_observations=0))
    print(json.dumps(read(root/'outcome.json'),sort_keys=True))

if __name__=='__main__':
    try:
        with (root/'probe.lock').open('x') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            main()
    except BaseException:
        (root/'native-failure.txt').write_text(traceback.format_exc());raise
