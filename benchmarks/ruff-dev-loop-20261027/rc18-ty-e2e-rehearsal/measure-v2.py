"""Measure one real Cargo invocation, retain its physical inputs/outputs, and exercise the native e2e."""
from pathlib import Path
import ast, collections, fcntl, hashlib, json, os, re, shutil, subprocess, sys, time

R=Path.home()/'.cache/ohm-18-ty-e2e-link-20261028'
label,scope,state,arm,*flags=sys.argv[1:]
assert flags in ([],['postprocess-complete-trace'])
resume=bool(flags)
assert re.fullmatch('[a-z0-9-]+',label) and scope in ('focused','workspace') and state in ('original','edited')
assert arm in ('rehearsal','release','candidate')
prep=json.loads((R/'prepared.json').read_bytes())
lock=(R/'measure.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
D=R/'reports'/label
if resume:
    assert D.is_dir() and not (D/'result.json').exists() and not (D/'list.stdout').exists()
else:
    D.mkdir()
src=R/'source';target=R/'target';shared=R/'shared'
store=R/'stores';(store/'objects').mkdir(exist_ok=True)
SDK=(R/'rustup/toolchains/ohm').resolve(strict=True)
assert SDK==(Path(prep['previous_sdk_for_rehearsal']) if arm=='rehearsal' else R/'install'/arm)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,data):p.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
def retain(p,digest):
    out=store/'objects'/digest
    if not out.exists():
        tmp=out.with_suffix('.part');shutil.copyfile(p,tmp);assert sha(tmp)==digest;tmp.rename(out)
    assert out.stat().st_size==p.stat().st_size
def st(p):
    s=p.stat();return {'dev':s.st_dev,'ino':s.st_ino,'size':s.st_size,'mtime_ns':s.st_mtime_ns}
def snapshots(when):
    names={};ron={}
    for root in (target,shared):
        for folder, dirs, files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('incremental','.fingerprint')]
            for fn in files:
                if fn.endswith(('.rlib','.rmeta')) and fn.startswith('lib'):
                    p=Path(folder)/fn
                    if not p.is_file():continue
                    key=str(p.relative_to(R));info=st(p); names[key]=info
                    if fn=='libron.rlib' or fn=='libron.rmeta' or fn.startswith('libron-'):
                        digest=sha(p); retain(p,digest);ron[key]=dict(info,sha256=digest)
    save(D/(when+'-rlibs.json'),names);save(D/(when+'-ron.json'),ron)
    return ron
assert shutil.disk_usage(R).free>33*2**30,shutil.disk_usage(R)
file=src/prep['file']
assert sha(file) in (prep['old_sha256'],prep['edited_sha256'])
b=file.read_bytes();before=b'return Some(offset.min(cell_range.end()));';after=b'return Some(offset);'
if state=='edited' and sha(file)==prep['old_sha256']:
    assert b.count(before)==1;file.write_bytes(b.replace(before,after))
elif state=='original' and sha(file)==prep['edited_sha256']:
    assert b.count(after)==1;file.write_bytes(b.replace(after,before))
assert sha(file)==prep['edited_sha256' if state=='edited' else 'old_sha256']
git_status=subprocess.check_output(['git','--no-optional-locks','-C',src,'status','--porcelain','-z'])
assert git_status==((b' M '+prep['file'].encode()+b'\0') if state=='edited' else b'')
env=dict(HOME=str(R/'home'),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',
         USER=os.environ['USER'],RUSTUP_HOME=str(R/'rustup'),RUSTUP_AUTO_INSTALL='0',
         CARGO_HOME=str(R/'cargo'),CARGO_BUILD_BUILD_DIR=str(shared),CARGO_TARGET_DIR=str(target),
         CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='8',CARGO_TERM_COLOR='never',TMPDIR=str(R/'tmp'),
         LC_ALL='C.UTF-8',LANG='C.UTF-8',GIT_OPTIONAL_LOCKS='0')
ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp']
for p in (D,target,shared,R/'cargo',R/'tmp',R/'home'):ns+=['--bind',str(p),str(p)]
ns+=['--chdir',str(src),'--']
sysroot=subprocess.check_output(ns+['rustc','+ohm','--print','sysroot'],env=env,text=True).strip()
assert Path(sysroot).resolve()==SDK
version=subprocess.check_output(ns+['cargo','+ohm','--version','--verbose'],env=env,text=True)
if arm=='release':assert '7caf399' in version,version
args=['cargo','+ohm','test']+(['--workspace'] if scope=='workspace' else ['-p','ty_server','--test','e2e'])+['--no-run','--locked','--offline','-j8','--message-format=json']
versions={name:sha(SDK/'bin'/name) for name in ('cargo','rustc','rustdoc')}
w=SDK/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
versions['wild']=sha(w);assert versions['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
if arm=='release':assert versions==json.loads((R/'release-images.json').read_bytes())
metadata={'scope':scope,'state':state,'arm':arm,'source':prep['source'],'source_sha256':sha(file),'argv':args,
                      'images':versions,'version':version,'empty_target':not any(target.iterdir()),'empty_shared':not any(shared.iterdir())}
trace=D/'trace'
if resume:
    original_metadata=json.loads((D/'command.json').read_bytes())
    assert all(original_metadata[k]==v for k,v in metadata.items() if k not in ('empty_target','empty_shared'))
    assert trace.is_dir() and any(trace.iterdir())
    exit_state=json.loads((D/'exit.json').read_bytes());assert exit_state['status']==0
    before_ron=json.loads((D/'before-ron.json').read_bytes())
    duration=exit_state['traced_seconds']
else:
    save(D/'command.json',metadata)
    before_ron=snapshots('before')
    trace.mkdir(); print('start',label,scope,state,arm,flush=True)
    start=time.monotonic()
    with (D/'cargo.stdout').open('xb') as out,(D/'cargo.stderr').open('xb') as err:
        p=subprocess.run(ns+['strace','-ff','-qq','-s','1048576','-e','trace=execve','-o',str(trace/'exec')]+args,
                         stdout=out,stderr=err,env=env,timeout=4800)
    duration=time.monotonic()-start;save(D/'exit.json',{'status':p.returncode,'traced_seconds':duration});assert p.returncode==0,(D/'cargo.stderr').read_text()[-2000:]
messages=[json.loads(l) for l in (D/'cargo.stdout').read_bytes().splitlines()]
assert messages[-1]=={'reason':'build-finished','success':True}
arts=[m for m in messages if m['reason']=='compiler-artifact']
exe,=[Path(a['executable']) for a in arts if a['target']['kind']==['test'] and a['target']['name']=='e2e' and '/crates/ty_server#' in a['package_id']]
assert exe.is_file()
native=[];counts=collections.Counter()
pattern=re.compile(rb'^execve\(("(?:(?:\\.)|[^"\\])*"),\s*(\[.*\]), (?:0x[\da-f]+|NULL).*?\)\s+= 0$')
for f in trace.glob('exec.*'):
    for line in f.read_bytes().splitlines():
        if not line.startswith(b'execve(') or not line.endswith(b'= 0'):continue
        m=pattern.match(line);assert m,(f,line[:140]); prog=Path(ast.literal_eval(m[1].decode()))
        if prog.name not in ('rustc','ld.bfd','ld.lld','rust-lld','ld','mold'):continue
        argv=ast.literal_eval(m[2].decode())
        if prog.name=='rustc' and '--crate-name' in argv:
            kind='link-only' if '-Zlink-only' in argv or any(s.startswith('link-only=') or s=='link-only' for s in argv) else 'full'
            ident=argv[argv.index('--crate-name')+1]
        elif prog.name=='ld.bfd' and prog.parent.name=='wild-ld':
            kind='wild';ident=argv[argv.index('-o')+1]
        elif prog.name=='rustc':continue
        else:
            kind='other-linker'
            ident=argv[argv.index('-o')+1] if '-o' in argv else str(prog)

        counts[kind]+=1
        native.append({'kind':kind,'id':ident,'pid':int(f.name.split('.')[-1]),'argv_sha256':hashlib.sha256(m[2]).hexdigest()})
save(D/'native.json',native)
links=[r for r in native if r['kind']=='wild' and Path(r['id']).name==exe.name]
elf=sha(exe);retain(exe,elf)
after_ron=snapshots('after')
env_test=dict(env,INSTA_UPDATE='no',NO_COLOR='1',RUST_BACKTRACE='0')
def run(key,argv):
    with (D/(key+'.stdout')).open('xb') as out,(D/(key+'.stderr')).open('xb') as err:
        val=subprocess.run(ns+list(map(str,argv)),env=env_test,stdout=out,stderr=err,timeout=125)
    return val.returncode
listing=run('list',[exe,'--list','--format','terse']); assert listing==0
tests=['notebook::hover_past_end_of_cell','notebook::inlay_hints_range_past_end_of_cell']
if scope=='focused' or label.endswith(('seed','edited','clean','restore')):
    results={}
    for i,case in enumerate(tests):
        assert (case+': test') in (D/'list.stdout').read_text()
        code=run('test-'+str(i),[exe,'--exact',case,'--test-threads=1','--nocapture'])
        output=(D/('test-'+str(i)+'.stdout')).read_text()
        assert 'running 1 test' in output and ('1 passed;' in output if code==0 else '1 failed;' in output)
        if state=='original':assert code==0,(case,(D/('test-'+str(i)+'.stderr')).read_text()[-900:])
        results[case]=code
else:results={}
ident=exe.name
rows=[]
for r in native:
    if r['kind']=='wild':
        dst=Path(r['id'])
        if dst.is_file() and dst.is_relative_to(R):
            rows.append({'file':str(dst.relative_to(R)),'size':dst.stat().st_size,'sha256':sha(dst)})
save(D/'linked-products.json',rows)
result={'label':label,'arm':arm,'state':state,'scope':scope,'units':len(arts),'fresh':sum(a['fresh'] for a in arts),
        'native':dict(counts),'full_crates':[r['id'] for r in native if r['kind']=='full'],
        'e2e_file':str(exe.relative_to(R)),'e2e_sha256':elf,'e2e_size':exe.stat().st_size,'e2e_link_count':len(links),
        'test_list_sha256':sha(D/'list.stdout'),'test_results':results,'traced_seconds':duration,
        'ron_before':{p:k['sha256'] for p,k in before_ron.items()},'ron_after':{p:k['sha256'] for p,k in after_ron.items()}}
save(D/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('full_crates','ron_before','ron_after')}),flush=True)
