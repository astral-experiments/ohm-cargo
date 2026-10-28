"""Qualify the first full Ruff test selection on two corrected -17 Cargo builds."""
from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,shutil,socket,subprocess,sys,traceback

p=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028');w=p/'ruff-evaluation-v2';k=Path(__file__).resolve().parent
assert socket.gethostname()=='charlie-ohm-c5-check-1025'
def read(f):return json.loads(f.read_bytes())
def save(f,data):
    t=f.with_suffix('.pending');t.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n');os.replace(t,f)
def sha(f):
    with f.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
sdk=Path(read(p/'sdk.json')['sdk']);src=Path(read(p/'ruff.json')['src']);can=w/'canonical';seed=w/'seed';scope='crates/ty_server/tests/e2e/inlay_hints.rs'
selected=['test','--no-run','--workspace'];excluded=[*selected,'--exclude','ty_server'];hash0='a025b90170c496d6336023fa8857c4d2cb2ef77c2e601bf119e9feb3c1a71624';hash1='24d443ea2c65e5879884b32e761fea2d5e0f3cd198fd0ea9a44bd27e52078fad'
def source():
    git=lambda *a:subprocess.check_output(['git','--no-optional-locks','-C',src,*a]);assert git('rev-parse','HEAD').decode().strip()==read(p/'ruff.json')['pin'] and not git('status','--porcelain','-z')
    assert hashlib.sha256(git('ls-files','-s','-z')).hexdigest()=='fc84f15ac7401cd9bdc362e4574c6d395529766c16be2e6b032ac47fa63d21cd' and sha(src/scope)==hash0 and sha(k/'ruff-edited-inlay-hints.rs')==hash1
def sealed_file(arm):
    exe=p/(arm+'-cargo');ident=read(p/(arm+'-cargo.json'))['sha'];assert len(ident)==64 and sha(exe)==ident;return exe,ident
def invocation(state,arm,edited,receipt):
    exe,ident=sealed_file(arm);proxy=str(Path(shutil.which('rustup')).parent)
    env=dict(HOME=str(can/'home'),PATH=proxy+':/usr/local/bin:/usr/bin:/bin',USER=os.environ.get('USER','dev-user'),RUSTUP_HOME=str(w/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(can/'cargo'),CARGO_TARGET_DIR=str(can/'target'),CARGO_BUILD_BUILD_DIR=str(can/'shared'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='8',CARGO_TERM_COLOR='never',TMPDIR=str(can/'tmp'),LANG='C.UTF-8',LC_ALL='C.UTF-8',GIT_OPTIONAL_LOCKS='0')
    ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(src),str(src),'--ro-bind',str(sdk),str(sdk),'--ro-bind',str(exe),str(sdk/'bin/cargo')]
    for n in ('target','shared','cargo','home','tmp'):ns+=['--bind',str(state/n),str(can/n)]
    if edited:ns+=['--ro-bind',str(k/'ruff-edited-inlay-hints.rs'),str(src/scope)]
    ns+=['--bind',str(receipt),str(receipt),'--chdir',str(src),'--'];return ns,env,ident
def actual(outer,state):
    path=Path(outer)
    for n in ('target','shared'):
        if path.is_relative_to(can/n):return state/n/path.relative_to(can/n)
    raise ValueError(outer)
def trace_jobs(d):
    pattern=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL).*?\)\s+= 0$');jobs=[]
    for f in sorted(d.glob('exec.*')):
        lines=f.read_bytes().splitlines()
        for line in lines:
            m=pattern.match(line)
            if not m:
                assert not(line.startswith(b'execve(') and line.endswith(b'= 0')),f;continue
            name=Path(ast.literal_eval(m[1].decode()));argv=ast.literal_eval(m[2].decode());action=None
            if name.name=='rustc' and name.samefile(sdk/'bin/rustc') and '--crate-name' in argv and argv[argv.index('--crate-name')+1] not in ('___','__'):
                target=argv[argv.index('--crate-name')+1];action='link-only' if any(v=='link-only' or v.startswith('-Zlink-only') for v in argv) else 'full'
            elif name.name in ('ld.bfd','ld.lld','ld','wild','wild-ld','rust-lld','mold') and '-o' in argv:
                target=argv[argv.index('-o')+1];action='wild' if name.samefile(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd') else 'other-linker'
            if action:
                term=re.search(rb'\+\+\+ exited with (\d+) \+\+\+',lines[-1]);assert term,(f,action);jobs.append(dict(pid=f.name,exe=str(name),argv=argv,kind=action,target=target,exit=int(term[1]),raw=hashlib.sha256(line).hexdigest()))
    return jobs
def build(state,arm,args,edited,receipt,traced):
    assert shutil.disk_usage(p).free>32*2**30;receipt.mkdir(parents=True);ns,env,ident=invocation(state,arm,edited,receipt)
    def run(a,**kw):return subprocess.run(ns+list(map(str,a)),env=env,**kw)
    for file,want in [(sdk/'bin/cargo',ident),(src/scope,hash1 if edited else hash0)]:assert run(['sha256sum',file],capture_output=True,check=True).stdout.decode().split()[0]==want
    assert run(['rustc','+ohm','--print','sysroot'],capture_output=True,check=True).stdout.decode().strip()==str(sdk)
    command=['cargo','+ohm',*args,'--locked','--offline','-j8','--message-format=json'];prefix=[]
    if traced:(receipt/'trace').mkdir();prefix=['strace','-ff','-q','-s','1048576','-e','trace=execve','-o',receipt/'trace/exec']
    with (receipt/'stdout').open('xb') as so,(receipt/'stderr').open('xb') as se:status=run([*prefix,*command],stdout=so,stderr=se).returncode
    save(receipt/'command.json',dict(command=command,code=status,traced=traced,arm=arm,binary=ident,edited=edited));assert status==0,(receipt,(receipt/'stderr').read_text()[-3000:]);events=[json.loads(l) for l in (receipt/'stdout').read_bytes().splitlines()];assert events[-1]=={'reason':'build-finished','success':True}
    rows=[j for j in events if j['reason']=='compiler-artifact'];diag=[j for j in events if j['reason']=='compiler-message'];roster=sorted(json.dumps({k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for r in rows);rh=hashlib.sha256(json.dumps(roster,separators=(',',':')).encode()).hexdigest();exes={r['executable'] for r in rows if r['executable']};natives={}
    for path in {n for r in rows for n in r['filenames']}|exes:
        f=actual(path,state)
        with f.open('rb') as fd:
            if fd.read(4)==b'\x7fELF':natives[path]=sha(f)
    workspace={n for r in rows if r['package_id'].startswith('path+') for n in [*r['filenames'],r['executable']] if n}
    assert exes<=workspace and exes<=natives.keys()
    registry={n:h for n,h in natives.items() if n not in workspace}
    natives={n:h for n,h in natives.items() if n in workspace}
    registry_digest=hashlib.sha256(json.dumps(registry,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert len(registry)==78 and registry_digest==read(k/'adopted-seed.json')['commands']['seed-repeat2']['registry_sha']
    save(receipt/'registry-native.json',registry)
    own,=[r for r in rows if r['target']['name']=='ty_server' and r['target']['kind']==['lib'] and Path(r['manifest_path']).parent.name=='ty_server' and not r['profile']['test']];out,=[n for n in own['filenames'] if n.endswith('.rlib')]
    e2e=[r['executable'] for r in rows if r['target']['name']=='e2e' and r['target']['kind']==['test'] and Path(r['manifest_path']).parent.name=='ty_server'];assert (len(e2e)==1 if edited else len(e2e)==0)
    if edited:
        assert (len(rows),len(natives),len(exes))==(619,110,102) and own['fresh'];listing=run([e2e[0],'--list'],capture_output=True,check=True);assert listing.stdout.count(b': test\n')>0 and not listing.stderr;(receipt/'e2e-list').write_bytes(listing.stdout)
    jobs=trace_jobs(receipt/'trace') if traced else None
    if jobs is not None:save(receipt/'physical.json',jobs)
    if edited and receipt.name.startswith('selected-'):
        snapshot=receipt/'native-files';snapshot.mkdir();saved={}
        for index,(path,digest) in enumerate(sorted(natives.items())):
            original=actual(path,state);dest=snapshot/str(index);subprocess.run(['cp','--reflink=auto',original,dest],check=True)
            assert not original.samefile(dest) and sha(dest)==digest;saved[path]=dict(file=dest.name,sha256=digest)
        save(receipt/'preserved-native.json',saved)
        snapshot=receipt/'registry-files';snapshot.mkdir();saved_registry={}
        for index,(path,digest) in enumerate(sorted(registry.items())):
            original=actual(path,state);dest=snapshot/str(index);subprocess.run(['cp','--reflink=auto',original,dest],check=True)
            assert sha(dest)==digest and not original.samefile(dest);saved_registry[path]=dict(file=dest.name,sha256=digest)
        save(receipt/'preserved-registry.json',saved_registry)
    meta=dict(units=len(rows),fresh=sum(r['fresh'] for r in rows),roster=rh,diagnostics=[(j['package_id'],j['message']) for j in diag],native=natives,exes=sorted(exes),ty_server=dict(file=out,sha=sha(actual(out,state)),fresh=own['fresh']),e2e=e2e,counts=dict(collections.Counter((j['kind'] if not j['exit'] else j['kind']+'-failed') for j in jobs)) if traced else None)
    save(receipt/'products.json',meta);print(receipt.name,'units',len(rows),'fresh',meta['fresh'],'ELF',len(natives),'jobs',meta['counts'],flush=True);return meta
def main(mode):
    source();os.sched_setaffinity(0,set(range(16)));l=(p/'combined-native-measure.lock').open('a');fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if mode=='seed':
        raise RuntimeError('The completed v2 seed is held at its original paths.')
    else:
        assert mode in ('observer','composed') and (w/'seed-complete.json').is_file();frozen=read(w/'seed-complete.json');state=w/('state-'+mode);assert not state.exists() and shutil.disk_usage(p).free>65*2**30
        subprocess.run(['cp','-a','--reflink=auto',str(seed),str(state)],check=True);rlib=frozen['ty_server']['file'];assert sha(actual(rlib,seed))==sha(actual(rlib,state))==frozen['ty_server']['sha'] and not actual(rlib,seed).samefile(actual(rlib,state));row=build(state,mode,selected,True,w/('selected-'+mode),True);assert row['ty_server']['sha']==frozen['ty_server']['sha'];again=build(state,mode,selected,True,w/('repeat-'+mode),True);assert again['roster']==row['roster'] and again['e2e']==row['e2e'];save(w/(mode+'-complete.json'),dict(first=row['counts'],repeat=again['counts'],first_e2e=row['e2e'],roster=row['roster']))
    source()
if __name__=='__main__':
    mode,=sys.argv[1:]
    try:main(mode)
    except BaseException:
        (p/('combined-v3-'+mode+'-failure.txt')).write_text(traceback.format_exc());raise
