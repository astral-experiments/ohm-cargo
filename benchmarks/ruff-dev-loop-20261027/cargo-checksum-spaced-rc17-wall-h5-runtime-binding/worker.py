"""Train four real Ruff states and time only admitted unchanged workspace test builds."""
import ast
import collections
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
import elf
from statistics_replication import analyze

here=Path(__file__).resolve().parent
host=Path.home()
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
q=p/'rc17-spaced-full-test-h5-v1';assets=q/'assets';logical=q/'work'
backing_home=host/'.cache/ohm-rc17-spaced-full-test-h5-v1'
source=host/'code/oss/ruff-ohm-whole-native-20261027'
reg=p/'cargo-checksum-migration-20261027-v1/states/test/seed/registry-home/registry'
logical_target=logical/'ruff-target';sdk=logical/'Ohm SDK';rustup=logical/'rustup'
driver='librustc_driver-774a793a844d5500.so'
std=Path('lib/rustlib/x86_64-unknown-linux-gnu')
plan=json.loads((here/'plan.json').read_bytes())
command=plan['clock']
ledger={}
floor={}

def read(f):return json.loads(f.read_bytes())
def put(f,v):
    f.parent.mkdir(parents=True,exist_ok=True)
    tmp=f.with_suffix(f.suffix+'.tmp')
    tmp.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n');os.replace(tmp,f)
def sha(f):
    with f.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def packed(v):return digest(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
def guard():
    for root in (p,host,Path('/dev/shm')):
        free=shutil.disk_usage(root).free
        floor[str(root)]=min(free,floor.get(str(root),free));assert free>25*2**30,(root,free)
def run(args,out,err,env=None):
    guard()
    with out.open('xb') as so,err.open('xb') as se:
        proc=subprocess.Popen([str(v)for v in args],env=env,stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
        try:
            while True:
                try:code=proc.wait(timeout=1);break
                except subprocess.TimeoutExpired:guard()
        except BaseException:
            os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise
    assert code==0,(args[-4:],code,err.read_bytes()[-500:])
def clean():
    git=lambda *a:subprocess.check_output(['git','--no-optional-locks','-C',str(source),*a])
    assert git('rev-parse','HEAD').decode().strip()==plan['reference_source']
    assert not git('status','--porcelain','-z') and digest(git('ls-files','-s','-z'))==plan['git_index_sha256']
def stable_records(arts):
    fields=('package_id','manifest_path','target','profile','features','filenames','executable')
    return sorted(json.dumps({k:v[k]for k in fields},sort_keys=True,separators=(',',':'))for v in arts)
def alias_state(block,arm):
    return (q if block==1 else backing_home)/'states'/('block-'+str(block))/arm
def registry_ledger(r):
    result={}
    for part in ('index','cache'):
        files=sorted(x for x in (r/part).rglob('*') if x.is_file());assert files
        # The physical sparse-registry namespace is host specific. Preserve it only in the private source ledger.
        for f in files:result[str(f.relative_to(r))]=[f.stat().st_size,sha(f)]
    return result
def setup():
    assert socket.gethostname()=='charlie-ohm-loader-perf-1024'
    clean();guard();assert shutil.disk_usage(p).free>65*2**30
    assert not logical.exists() and not backing_home.exists();backing_home.mkdir(mode=0o700);logical.mkdir(mode=0o700)
    for n in ('ruff-target','shared','home','cargo','Ohm SDK'):(logical/n).mkdir(mode=0o700)
    (rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(sdk,target_is_directory=True)
    orig=read(assets/'transfer-manifest.json')
    assert len(orig)==81 and sha(assets/'transfer-manifest.json')=='20b7c12df9d4a24f161f1d08f0003ebe2eeba719d0d0ced0f34ded1b001e923b'
    assert all([ (assets/k).stat().st_size,sha(assets/k),(assets/k).stat().st_mode&0o777]==v for k,v in orig.items())
    for a in 'BC':
        rv=q/('view-'+a)
        for sub in ('lib','bin'):(rv/sub).mkdir(parents=True)
        # Keep the compiler frontend and driver physically within the intended effective SDK.
        for name,part in [('cargo','bin/cargo'),('rustc','bin/rustc'),('driver.so','lib/'+driver)]:
            src=assets/a/name;dst=rv/part;shutil.copy2(src,dst);assert src.stat().st_ino!=dst.stat().st_ino
        for sub in ('lib','bin'):
            for file in sorted((assets/'common'/sub).iterdir()):
                dest=rv/sub/file.name
                if file.name=='rustlib':dest.mkdir()
                else:dest.symlink_to(file,target_is_directory=file.is_dir())
    r = registry_ledger(reg);put(q/'registry-manifest.private.json',r)
    cpu=subprocess.check_output(['lscpu'],text=True)
    m= {'release_inputs':plan['images'],'runtime_ledger':sha(assets/'transfer-manifest.json'),'common_sdk_ledger':packed({k:v for k,v in orig.items() if k.startswith('common/')}),
        'logical':{'sdk':str(sdk),'registry':str(logical/'cargo'),'target':str(logical_target),'build':str(logical/'shared'),'source':str(source),'rustup':str(rustup)},
        'registry':{'files':len(r),'bytes':sum(v[0]for v in r.values()),'private_manifest_sha':sha(q/'registry-manifest.private.json')},'tool_auth':{n:sha(Path(shutil.which(n)).resolve())for n in ('bwrap','strace','rustup','cc','git','python3')},
        'paths':{'block1':str(alias_state(1,'B').parent),'block2':str(alias_state(2,'B').parent)},'cpus':sorted(os.sched_getaffinity(0)),'kernel':os.uname().release,'lscpu':cpu,'source_index':plan['git_index_sha256'],'source_lock':sha(source/'Cargo.lock'),'floor':floor,'elf_selftest':elf.selftest()}
    put(q/'preflight.json',m)
def environment():
    return dict(HOME=str(logical/'home'),USER='dev-user',PATH=str(host/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',CARGO_HOME=str(logical/'cargo'),CARGO_TARGET_DIR=str(logical_target),CARGO_BUILD_BUILD_DIR=str(logical/'shared'),CARGO_BUILD_JOBS='4',CARGO_NET_OFFLINE='true',RUSTUP_HOME=str(rustup),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',GIT_OPTIONAL_LOCKS='0',LANG='C.UTF-8',LC_ALL='C.UTF-8')
def ns(block,a,dest):
    state=alias_state(block,a)
    route=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(q/('view-'+a)),str(sdk),'--ro-bind',str(assets/'common/lib/rustlib'),str(sdk/'lib/rustlib')]
    for n in ('target','shared','cargo','home'):route+=['--bind',str(state/n),str(logical_target if n=='target' else logical/n)]
    return route+['--bind',str(dest),str(dest),'--chdir',str(source),'--']
def binding(block,a,dest):
    route=ns(block,a,dest);env=environment()
    values={sdk/'bin/cargo':plan['images'][a]['cargo_sha'],sdk/'bin/rustc':plan['images'][a]['frontend'],sdk/'lib'/driver:plan['images'][a]['driver'],sdk/std/'bin/wild-ld/ld.bfd':plan['images'][a]['wild']}
    actual=subprocess.check_output(route+['sha256sum',*map(str,values)],env=env,text=True).splitlines()
    assert {Path(line.split('  ',1)[1]):line.split('  ',1)[0]for line in actual}==values
    root=subprocess.check_output(route+['rustc','+ohm','--print=sysroot'],env=env,text=True).strip();assert root==str(sdk)and ' ' in root
    version={k:subprocess.check_output(route+[k,'+ohm','-Vv'],env=env,text=True)for k in ('cargo','rustc')}
    return {'effective_sdk':root,'hashes':{str(k.relative_to(sdk)):v for k,v in values.items()},'version':version}
def newstate(b,a):
    st=alias_state(b,a);assert not st.exists()
    st.mkdir(parents=True,mode=0o700);assert not list(st.iterdir())
    for n in ('home','shared','target'):(st/n).mkdir()
    sub=st/'cargo/registry';sub.mkdir(parents=True)
    for n in ('index','cache'):subprocess.run(['cp','-a','--reflink=auto','--',str(reg/n),str(sub/n)],check=True)
    orig=read(q/'registry-manifest.private.json');assert registry_ledger(sub)==orig
    assert all((reg/k).stat().st_dev!=(sub/k).stat().st_dev or (reg/k).stat().st_ino!=(sub/k).stat().st_ino for k in orig)
def traces(dest):
    jobs=[];links=[];others=collections.Counter();images=[];raw_sha=[]
    for f in sorted((dest/'trace').glob('exec.*')):
        b=f.read_bytes();pending=None;matches=re.findall(rb'\+\+\+ exited with (\d+) \+\+\+',b);ex=int(matches[-1])if matches else None; raw_sha.append([f.name,digest(b)])
        for line in b.splitlines():
            if line.startswith((b'execve(',b'execveat(')) and line.endswith(b'<unfinished ...>'):
                assert pending is None;pending=line.removesuffix(b'<unfinished ...>');continue
            if m:=re.match(rb'^<\.\.\. (execve(?:at)?) resumed>(.*)$',line):assert pending is not None;line=pending+m[2];pending=None
            if not line.startswith((b'execve(',b'execveat('))or not re.search(rb'\)\s+= 0$',line):continue
            m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m
            image=ast.literal_eval(m[1].decode());v=ast.literal_eval(m[2].decode());name=Path(image).name;images.append(image);others[name]+=1
            if name=='rustc' and '--crate-name' in v and '--out-dir'in v and '--print=file-names' not in v:
                cn=v[v.index('--crate-name')+1]
                if cn in ('___','__'):continue
                mode='link-only' if any(f in ('-Zlink-only','-Zlink-only=yes')for f in v)or any(k=='-Z' and t.split('=')[0]=='link-only' for k,t in zip(v,v[1:]))else'full'
                jobs.append([mode,cn,f.name,digest(m[2]),ex]);assert ex==0
            if name=='ld.bfd' and 'wild-ld'in Path(image).parts:
                links.append([Path(v[v.index('-o')+1]).name,f.name,digest(m[2]),ex]);assert ex==0
        assert pending is None
    put(dest/'processes.json',{'rustc':jobs,'wild':links,'other_images':dict(others),'full_trace_sha256':packed(raw_sha)})
    return jobs,links,set(images)
def roster_touch(b,a,dest):
    data=[json.loads(l) for l in (dest/'stdout').read_bytes().splitlines()]
    assert data[-1]=={'reason':'build-finished','success':True}
    arts=[v for v in data if v['reason']=='compiler-artifact'];assert len(arts)==619
    units=stable_records(arts);messages=sorted(json.dumps(v,sort_keys=True,separators=(',',':'))for v in data if v['reason']=='compiler-message')
    exes=sorted(v['executable'] for v in arts if v['executable']);harness=[v for v in arts if v['executable']and v['profile']['test']]
    assert len(set(exes))==len(exes)==102 and len(harness)==84
    paths=set()
    for v in arts:
        if not v['package_id'].startswith('path+'):continue
        for name in v['filenames']:
            f=Path(name)
            if f.suffix not in ('','.so') or not f.is_relative_to(logical_target):continue
            rel=f.relative_to(logical_target)
            with (alias_state(b,a)/'target'/rel).open('rb') as o:
                if o.read(4)==b'\x7fELF':paths.add(str(rel))
    assert len(paths)==110 and {str(Path(x).relative_to(logical_target))for x in exes}<=paths
    selected,=[v['executable'] for v in harness if v['target']['name']=='e2e'and Path(v['manifest_path']).parent.name=='ty_server']
    guards={'units':len(units),'roster':packed(units),'diagnostics':packed(messages),'executables':len(exes),'executables_sha':packed(exes),'harness_profile':len(harness),'nonharness_profile':len(exes)-len(harness),'native_paths':sorted(paths),'harness':selected}
    put(dest/'roster.json',{'units':units,'diagnostics':messages,'executables':exes});return guards,data
def products(b,a,paths):
    return {n:sha(alias_state(b,a)/'target'/n)for n in paths}
def oracle(b,a,dest,target):
    run(ns(b,a,dest)+[target,'--list','--format','terse'],dest/'list.stdout',dest/'list.stderr',environment())
    raw=(dest/'list.stdout').read_bytes();assert b'inlay_hints::default_inlay_hints: test' in raw
    return [digest(raw),sha(dest/'list.stderr'),len(raw.splitlines())]
def state_label(b,a):return str(b)+'-'+a
def observe(b,a,tag):
    dest=q/'receipts'/state_label(b,a)/tag;dest.mkdir(parents=True);(dest/'trace').mkdir()
    sub=ns(b,a,dest);actual=binding(b,a,dest);put(dest/'binding.json',actual)
    argv=command+['--message-format=json'];trace=['strace','-ff','-q','-s','1048576','-e','trace=execve,execveat','-e','signal=none','-o',str(dest/'trace/exec')]
    run(sub+trace+argv,dest/'stdout',dest/'stderr',environment());assert b'Blocking waiting'not in(dest/'stderr').read_bytes()
    g,data=roster_touch(b,a,dest);jobs,links,imgs=traces(dest);exes=set(v['executable']for v in data if v.get('executable'));assert not exes.intersection(imgs)
    counts=collections.Counter(v[0]for v in jobs)
    dirty=sorted(v['target']['name'] for v in data if v['reason']=='compiler-artifact' and not v['fresh'])
    row={'block':b,'arm':a,'tag':tag,'command':argv,'status':0,'full':counts['full'],'link_only':counts['link-only'],'wild':len(links),'fresh':619-len(dirty),'dirty':dirty,'rustc_full_names':sorted(v[1]for v in jobs if v[0]=='full'),'products':products(b,a,g['native_paths']),'guards':g,'oracle':oracle(b,a,dest,g['harness']),'stdout':sha(dest/'stdout'),'stderr':sha(dest/'stderr'),'physical':sha(dest/'processes.json'),'source':plan['reference_source'],'floors':floor}
    put(dest/'result.json',row);print('native',b,a,tag,row['fresh'],row['full'],row['link_only'],row['wild'],flush=True)
    if tag=='cold':assert row['full']>=600 and row['wild']>=110
    elif tag in ('qual-1','qual-2','post-clock'):
        assert [row['full'],row['link_only'],row['wild']]==([1,50,50] if a=='B' else [0,0,0])
        assert row['rustc_full_names']==(['ron']if a=='B'else[]) and (a=='B' or row['fresh']==619)
    return row
def regpath(b,a):return q/'receipts'/state_label(b,a)/'qual-2/result.json'
def train(b,a):
    clean();newstate(b,a);rows=[observe(b,a,n)for n in ['cold','transitional','qual-1','qual-2']]
    assert rows[-2]['guards']==rows[-1]['guards'] and rows[-2]['oracle']==rows[-1]['oracle'] and rows[-2]['dirty']==rows[-1]['dirty']
    clean()
    return rows[-1]
def check_native(b,a,row,ref,fields):
    st=alias_state(b,a);assert set(row)==set(ref);out={}
    for n,sig in row.items():
        if sig==ref[n]:continue
        right=elf.normalize(st/'target'/n);left=fields[n];assert right['normalized']==left['normalized'] and right['bytes']==left['bytes'] and right['rodata_entsize']!=left['rodata_entsize'] and min(right['rodata_entsize'],left['rodata_entsize'])==0 and right['build_id']!=left['build_id'],(b,a,n,right,left)
        out[n]=[left['rodata_entsize'],right['rodata_entsize'],left['build_id'],right['build_id']]
    return out
def qualify():
    ordered=[(1,'B'),(1,'C'),(2,'C'),(2,'B')]
    first=read(regpath(1,'B'));ref=first['products'];st=alias_state(1,'B')
    fields={n:elf.normalize(st/'target'/n)for n in ref}
    out={}
    for b,a in ordered:
        state=read(regpath(b,a));assert state['guards']==first['guards'] and state['oracle']==first['oracle']
        assert products(b,a,state['guards']['native_paths'])==state['products']
        out[state_label(b,a)]={'source':sha(regpath(b,a)),'variation':check_native(b,a,state['products'],ref,fields)}
    put(q/'baseline-elf-fields.json',fields);put(q/'qualified.json',{'arm_receipts':out,'reference_products':ref,'gates':first['guards'],'oracle':first['oracle'],'ready':True})
def slot(b,a,j):
    dest=q/'wall'/('block-'+str(b))/f'{j:02}-{a}';dest.mkdir(parents=True)
    run(ns(b,a,dest)+['/usr/bin/python3','-B',str(here/'clock.py'),str(dest),*command],dest/'outer.stdout',dest/'outer.stderr',environment())
    assert (dest/'outer.stdout').stat().st_size==(dest/'outer.stderr').stat().st_size==(dest/'stdout').stat().st_size==0
    stderr=(dest/'stderr').read_bytes();assert b'Finished' in stderr and b'Blocking waiting'not in stderr
    n=len(re.findall(rb'^\s*Compiling\s+',stderr,re.M)); assert (a=='B' and n>0) or (a=='C' and n==0),(b,a,j,n)
    clock=read(dest/'clock.json');assert clock['returncode']==0 and clock['elapsed_ns']==clock['stop']-clock['start']>0 and clock['argv']==command
    qual=read(q/'qualified.json');vals=products(b,a,qual['gates']['native_paths']);proof=check_native(b,a,vals,qual['reference_products'],read(q/'baseline-elf-fields.json'))
    if a=='C':assert vals==read(regpath(b,a))['products']
    checks=oracle(b,a,dest,qual['gates']['harness']);assert checks==qual['oracle']
    put(dest/'verified.json',{'ns':clock['elapsed_ns'],'stdout':sha(dest/'stdout'),'stderr':sha(dest/'stderr'),'stdout_bytes':0,'compiler_progress_lines':n,'products':vals,'variation':proof,'harness':checks})
    return clock['elapsed_ns']
def score():
    assert not(q/'wall').exists()
    scope=read(here/'score-grant.json');assert scope['qualification']==sha(q/'qualified.json') and scope['protocol']==sha(here/'SHA256SUMS') and scope['plan']=='eeff437a2d827c20e19d0ca66de145c8e2d2ccb9' and len(scope['binding_commit'])==40
    allrows=[];clean()
    for b,orders in enumerate(plan['orders'],1):
        rows=[]
        for j,order in enumerate(orders,1):
            vals={a:slot(b,a,j)for a in order};rows.append({'order':order,'ns':vals});put(q/'wall'/f'ledger-{b}.json',rows)
        allrows.append(rows)
    for b,a in [(1,'B'),(1,'C'),(2,'B'),(2,'C')]:
        row=observe(b,a,'post-clock');base=read(regpath(b,a));assert row['dirty']==base['dirty']and row['guards']==base['guards']and row['oracle']==base['oracle']
        ref=read(q/'qualified.json');check_native(b,a,row['products'],ref['reference_products'],read(q/'baseline-elf-fields.json'))
    clean();guard();put(q/'wall/all.json',allrows);put(q/'wall/result.json',analyze(allrows,plan));put(q/'wall/complete.json',{'grant':sha(here/'score-grant.json'),'rows':sha(q/'wall/all.json'),'wall_commands':24,'native_post_commands':4})
def main():
    assert socket.gethostname()=='charlie-ohm-loader-perf-1024' and sorted(os.sched_getaffinity(0))==list(range(8))
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True);clean()
    with (p/'native-measure.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);guard();mode=sys.argv[1]
        if mode=='setup':setup()
        elif mode=='train':
            for b,as_ in [(1,'BC'),(2,'CB')]:
                for a in as_:train(b,a)
            qualify()
        elif mode=='score':score()
        else:raise ValueError(mode)
if __name__=='__main__':
    try:main()
    except BaseException:
        with contextlib.suppress(Exception):
            dest=q/('failure-'+sys.argv[1]+'-'+str(time.time_ns())+'.txt');dest.write_text(traceback.format_exc())
        raise
