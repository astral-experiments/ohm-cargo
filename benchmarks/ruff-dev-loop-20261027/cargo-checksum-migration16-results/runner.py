"""Observe same-path full-workspace migration runs under the native lock; no flags change between arms."""
import ast, collections, fcntl, hashlib, json, os, re, shutil, signal, subprocess, sys, time
from pathlib import Path
H=Path.home(); W=H/'code/oss/ruff-ohm-whole-native-20261027'; P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027'); D=P/'cargo-checksum-migration-20261027-v1'
X=H/'.cache/ohm-233-position-qualified-20261027'; donor=X/'first-occurrence-classic-pr233-h5-v2/state/test/C/registry-home'
O=D/'evidence';O.mkdir(exist_ok=True); paths=('target','shared','registry-home');SDK=D/'sdk'; NEW=D/'subjects'/'new-cargo'
VERIFIED='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568'
SOURCESHA='93526150df078af7dd8fc4226cdcc469539d2001'
FLOOR=25*2**30; DISKS=(D,H,Path('/dev/shm')); minfree={str(q):shutil.disk_usage(q).free for q in DISKS}
for n in paths: (D/n).mkdir(exist_ok=True)
def h(p):
    with p.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
def hh(b):return hashlib.sha256(b).hexdigest()
def save(p,r):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n');os.replace(tmp,p)
def guard():
    for p in DISKS:
        f=shutil.disk_usage(p).free;minfree[str(p)]=min(minfree[str(p)],f);assert f>FLOOR,(p,f)
def run(argv,env,out,err,wd=None):
    guard()
    with out.open('wb')as a,err.open('wb')as b:
        task=subprocess.Popen(list(map(str,argv)),env=env,cwd=wd,stdout=a,stderr=b,start_new_session=True)
        try:
            while True:
                try:return task.wait(timeout=1)
                except subprocess.TimeoutExpired:guard()
        except BaseException:
            os.killpg(task.pid,signal.SIGTERM);task.wait();raise
def environment():
    return dict(HOME=str(H),PATH=str(H/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',RUSTUP_HOME=str(D/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(D/'registry-home'),CARGO_TARGET_DIR=str(D/'target'),CARGO_BUILD_BUILD_DIR=str(D/'shared'),CARGO_BUILD_JOBS='8',CARGO_NET_OFFLINE='true',GIT_OPTIONAL_LOCKS='0',LC_ALL='C.UTF-8')
def ns(state,img,rec,wd=W):
    return ['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp',*[x for n in paths for x in ['--bind',str(state/n),str(D/n)]],'--bind',str(rec),str(rec),'--ro-bind',str(img),str(SDK/'bin/cargo'),'--chdir',str(wd),'--']
def command(mode):
    return ['cargo','+ohm',mode]+(['--no-run']if mode=='test' else [])+['--workspace','--locked','--offline','--message-format=json']
def original():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip()==SOURCESHA
    assert subprocess.check_output(['git','status','--porcelain','-uno'],cwd=W)==b''
def translate(p,state):
    for n in paths:
        if p.is_relative_to(D/n):return state/n/p.relative_to(D/n)
    return p
def read_jobs(rec):
    calls=[];digests=[];aux=c.Counter() if False else collections.Counter()
    for fn in sorted(rec.glob('exec.*')):
        if not fn.suffix[1:].isdigit():continue
        t=fn.read_text(errors='replace');pid=int(fn.suffix[1:]);e=re.findall(r'\+\+\+ (?:exited with (\d+)|killed by (\w+))',t);ex=(int(e[-1][0])if e and e[-1][0]else (e[-1][1] if e else None))
        d=h(fn)
        if 'execve('in t:digests.append((fn.name,d))
        for l in t.splitlines():
            m=re.match(r'^execve\("([^"]+)", (\[.*\]), .+ = 0$',l)
            if not m:continue
            try:a=ast.literal_eval(m[2])
            except (ValueError,SyntaxError): raise RuntimeError(('successful exec could not decode',fn,len(l)))
            p=Path(m[1]);name=p.name;source=next((x for x in a if x.endswith(('.rs','.rlink'))),None);cn=None;roles=[];em=next((x for x in a if x.startswith('--emit=')),None)
            if p.resolve()==(SDK/'bin/rustc').resolve():
                if '--crate-name'in a:cn=a[a.index('--crate-name')+1]
                relink=any(x in ['-Zlink-only','-Zlink-only=yes']for x in a)or any(x=='-Z'and y.split('=')[0]=='link-only'for x,y in zip(a,a[1:]))
                roles=['rustc-link-only']if relink else (['rustc-full']if cn and source and em else ['rustc-query'])
            elif '/wild-ld/'in str(p):roles=['wild']
            elif name=='collect2':roles=['collect2']
            elif name in ('cc','gcc','gcc-13','x86_64-linux-gnu-gcc','x86_64-linux-gnu-gcc-13'):roles=['cc']
            elif name.startswith(('build-script-build','build_script_build'))and('/run/'in str(p)or'/build/'in str(p)):roles=['build-script']
            for role in roles:
                opt=next((a[i+1]for i,x in enumerate(a[:-1])if x=='-o'),None);argsha=hh(m[2].encode())
                calls.append({'role':role,'pid':pid,'exit':ex,'crate':cn,'source':source,'arg_sha256':argsha,'exe':str(p),'output':Path(opt).name if opt else None,'raw_file_sha256':d})
            if not roles:aux[name]+=1
    return calls,digests,dict(aux)
def process(mode,stage,tag,state,img):
    rec=O/mode/stage/tag;rec.mkdir(parents=True,exist_ok=False)
    assert img.is_file()
    # The canonical Cargo and Rust compiler hashes prove which image the namespace actually uses.
    m=ns(state,img,rec);env=environment();drv,=(SDK/'lib').glob('librustc_driver*.so');wild,=(SDK/'lib/rustlib').glob('*/bin/wild-ld/ld.bfd')
    bind_paths=[SDK/'bin/cargo',SDK/'bin/rustc',drv,wild,W/'Cargo.lock']
    binding=subprocess.check_output(m+['sha256sum',*map(str,bind_paths)],env=env,text=True);(rec/'binding.txt').write_text(binding)
    assert binding.split()[0]==h(img)
    argv=command(mode)
    rc=run(m+['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',str(rec/'exec'),*argv],env,rec/'cargo.stdout.ndjson',rec/'cargo.stderr')
    data=[json.loads(b)for b in(rec/'cargo.stdout.ndjson').read_bytes().splitlines() if b.strip()];a=[d for d in data if d['reason']=='compiler-artifact'];msgs=[{'package':d['package_id'],'target':d['target']['name'],'message':d['message']}for d in data if d['reason']=='compiler-message'];scripts=[d for d in data if d['reason']=='build-script-executed']
    prod={};art=[]
    for r in a:
        v=dict(pkg=r['package_id'],name=r['target']['name'],profile=r['profile'],kind=r['target']['kind'],source=r['target']['src_path'],fresh=r['fresh'],files=r['filenames'],exe=r['executable'])
        art.append(v)
        for name in r['filenames']+([r['executable']] if r['executable']else []):
            if name in prod:continue
            p=translate(Path(name),state)
            if p.is_file():
                with p.open('rb')as f:head=f.read(8)
                prod[name]={'bytes':p.stat().st_size,'sha256':h(p),'elf':head.startswith(b'\x7fELF'),'kind':v['kind'],'workspace':v['pkg'].split('#',1)[0].startswith(W.as_uri().replace('file:','path+file:')+'/'),'name':v['name']}
            else:prod[name]={'missing':True}
    calls,raw,aux=read_jobs(rec);types=dict(collections.Counter(v['role']for v in calls));hist={'command':argv,'exit':rc,'units':len(a),'fresh':sum(x['fresh'] for x in a),'physical':types,'cargo_image':h(img),'compiler':h(SDK/'bin/rustc'),'driver':h(drv),'linker':h(wild),'diag':len(msgs),'elf':sum(v.get('elf',False)for v in prod.values()),'native_hash_rows':len(prod),'source':SOURCESHA,'lock':h(W/'Cargo.lock'),'raw_binding':h(rec/'binding.txt'),'stdout':h(rec/'cargo.stdout.ndjson'),'stderr':h(rec/'cargo.stderr'),'physical_sha':None,'floor':dict(minfree)}
    save(rec/'calls.json',calls);save(rec/'exec-ledger.json',raw);save(rec/'other-execs.json',aux);save(rec/'files.json',prod);save(rec/'artifacts.json',art);save(rec/'diagnostics.json',msgs);save(rec/'scripts.json',scripts)
    hist['physical_sha']=h(rec/'calls.json');hist['files_sha']=h(rec/'files.json');hist['artifact_sha']=h(rec/'artifacts.json');save(rec/'receipt.json',hist)
    print(mode,stage,tag,rc,len(a),hist['fresh'],types,flush=True)
    assert rc==0 and len(a)=={'check':520,'build':501,'test':619}[mode],(mode,stage,tag,hist,(rec/'cargo.stderr').read_text()[-600:])
    return hist
def seed(mode):
    state=D/'states'/mode/'seed';img=SDK/'bin/cargo';assert h(img)==VERIFIED
    state.mkdir(parents=True);(state/'target').mkdir();(state/'shared').mkdir()
    assert donor.is_dir()and shutil.disk_usage(D).free>FLOOR+17*2**30
    subprocess.run(['cp','-a','--reflink=auto',donor,state/'registry-home'],check=True)
    h0=process(mode,'seed','cold',state,img);assert h0['physical'].get('rustc-full',0)>0
    for n in range(1,5):
        a=process(mode,'seed','noop-'+str(n),state,img)
        if a['fresh']==a['units'] and not any(a['physical'].get(k,0)for k in ('rustc-full','rustc-link-only','build-script','wild')):
            save(O/mode/'seed-complete.json',{'final':'noop-'+str(n),'receipt':a,'filesystem':dict(minfree)});break
    else:raise AssertionError((mode,'seed did not settle'))
if __name__=='__main__':
    original();guard()
    assert set(os.sched_getaffinity(0))==set(range(24))
    with (P/'native-measure.lock').open('rb')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for mode in sys.argv[1:]:
            assert mode in ['check','build','test'];seed(mode)
    original()
