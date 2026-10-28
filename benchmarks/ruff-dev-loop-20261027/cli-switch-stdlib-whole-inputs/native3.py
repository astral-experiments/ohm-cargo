"""Observe real alternating Ruff and Ty builds on the named historical edit. All command times are unscored."""
from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time
h=Path.home();p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');w=h/'code/oss/ruff-ohm-whole-native-20261027';q=p/'cli-switch-native609e-v1';t,s,r=[q/n for n in ('target','shared','registry-home')]; tmp=Path('/dev/shm/ohm-cli-switch-native609e-v1'); usr=Path('/run/user/1000/ohm-cli-switch-native609e-v1');repo=q/'records'; archive=h/'.cache/ohm-cli-switch-609e-native-v1'; source=q/'binding.json';binding=json.loads(source.read_text()); f=Path(binding['source_file']);folder=Path(binding['fixture_dir']); rp=p/'build-script-producer-reuse16-v1'; mins={}
limits={p:25*2**30,h:25*2**30,Path('/dev/shm'):25*2**30,usr:750*2**20}
def guard():
    for path,limit in limits.items():
        free=shutil.disk_usage(path).free;mins[str(path)]=min(free,mins.get(str(path),free));assert free>limit,(str(path),free,limit)
def sha(path):
    with path.open('rb')as st:return hashlib.file_digest(st,'sha256').hexdigest()
H=lambda b:hashlib.sha256(b).hexdigest()
def dump(path,v):path.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def load(path):return json.loads(path.read_text())
def real(path,st):
    qpath=Path(path)
    for pos,n in [(t,'target'),(s,'shared'),(r,'registry-home')]:
        if qpath.is_relative_to(pos):return st/n/qpath.relative_to(pos)
    return qpath
env=dict(HOME=str(h),PATH=str(h/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',LC_ALL='C.UTF-8',RUSTUP_HOME=str(rp/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(r),CARGO_TARGET_DIR=str(t),CARGO_BUILD_BUILD_DIR=str(s),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='6',GIT_OPTIONAL_LOCKS='0')
def space(path):return {n:shutil.disk_usage(n).free for n in map(str,limits)}
def stable():assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=w,text=True).strip()==binding['pin'] and subprocess.check_output(['git','status','--porcelain','-uno'],cwd=w)==b''
def namespace(st,view,rec):
    v=q/('before' if view=='original'else'edited')
    return ['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(rec),str(rec),*[z for n,dst in [('target',t),('shared',s),('registry-home',r)]for z in ['--bind',str(st/n),str(dst)]],'--ro-bind',str(v/f),str(w/f),'--ro-bind',str(v/folder),str(w/folder),'--chdir',str(w),'--']
def monitored(argv,cout,cerr):
    guard()
    with cout.open('wb')as o,cerr.open('wb')as e:
        child=subprocess.Popen(argv,env=env,stdout=o,stderr=e,start_new_session=True)
        try:
            while True:
                try:ret=child.wait(timeout=1);break
                except subprocess.TimeoutExpired:guard()
        except BaseException:os.killpg(child.pid,signal.SIGTERM);child.wait();raise
    assert ret==0,(ret,cerr.read_text(errors='replace')[-500:])
def dep_receipt(st,paths):
    out={}
    for name,loc in paths.items():
        fp=real(loc,st)
        if fp.is_file():out[name]={'name':fp.name,'bytes':fp.stat().st_size,'sha256':sha(fp)}
        else:out[name]={'missing':str(loc)}
    return out
def call(state,select,view,phase):
    st=state;rec=repo/(state.name+'-'+phase+'-'+select)
    if state.name=='seed' and (rec/'result.json').is_file():return load(rec/'result.json')
    recover=(state.name=='seed' and phase=='cold' and select in ('ruff','ty') and (rec/'stdout').is_file());
    if not recover:rec.mkdir()
    ns=namespace(state,view,rec)
    got=subprocess.check_output(ns+['sha256sum',str(w/f)],env=env,text=True).split()[0];assert got==binding['source_blobs'][view]
    md=w/folder/'undefined-name.md';assert subprocess.run(ns+['test','-f',md],env=env).returncode==(0 if view=='original'else 1)
    cmd=['cargo','+ohm','build','--locked','--offline','--message-format=json','-p',select,'--bin',select]
    if not recover:monitored(ns+['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',str(rec/'exec'),*cmd],rec/'stdout',rec/'stderr')
    messages=[json.loads(l) for l in (rec/'stdout').read_bytes().splitlines()];assert messages[-1]=={'reason':'build-finished','success':True};arts=[a for a in messages if a['reason']=='compiler-artifact']
    outputs={};unit=[]
    for a in arts:
        allowed=a['package_id'].startswith('path+file://'+str(w)+'/')
        paths=a['filenames']+([a['executable']]if a.get('executable')else[])
        unit.append({'pkg':a['package_id'].split('#')[-1], 'kind':a['target']['kind'],'name':a['target']['name'],'features':a['features'],'fresh':a['fresh'],'profile':a['profile'],'files':paths})
        if not allowed:continue
        for dest in paths:
            if dest in outputs:continue
            pp=real(dest,st);assert pp.is_file()
            outputs[dest]={'sha':sha(pp),'size':pp.stat().st_size,'pkg':a['target']['name'],'source':a['target']['src_path'],'kinds':a['target']['kind']}
    rows=[];intern=[]
    for path in sorted(rec.glob('exec.*')):
        rr=path.read_bytes();content=rr.decode(errors='replace');exits=re.findall(r'\+\+\+ exited with (\d+) \+\+\+',content)
        for line in content.splitlines():
            mat=re.match(r'^execve\((".*?"), (\[.*\]), .* = 0$',line)
            if not mat:continue
            image=ast.literal_eval(mat[1]);a=ast.literal_eval(mat[2]);nm=Path(image).name
            role=None;name=None;src=next((v for v in a if v.endswith(('.rs','.rlink'))),None)
            if nm=='rustc':
                if any(v in ('link-only','-Zlink-only','-Zlink-only=yes')for v in a):role='link-only'
                elif '--crate-name'in a and src and any(v.startswith('--emit=')for v in a):role='full';name=a[a.index('--crate-name')+1]
            elif '/wild-ld/' in image:role='wild'
            elif nm=='collect2':role='collect2'
            elif nm in ('cc','gcc','gcc-13','x86_64-linux-gnu-gcc-13'):role='cc'
            elif nm.startswith(('build_script_build','build-script-build'))and('/run/'in image or'/build/'in image):role='script'
            if not role:continue
            row={'role':role,'crate':name,'source':src,'pid':path.name,'raw_sha256':H(rr),'argv_sha256':H(json.dumps(a,separators=(',',':')).encode()),'exit':int(exits[-1])if exits else None}
            if role=='full':
                od=a[a.index('--out-dir')+1];row['unit_id']=Path(od).parent.name
                if name=='ruff_python_stdlib':
                    arg={v.split('=',1)[0]:v.split('=',1)[1]for i,k in enumerate(a[:-1])if k=='--extern'and '='in(v:=a[i+1])}
                    files={k:v for k,v in outputs.items()if v['pkg']==name}
                    intern.append({'source_sha':got,'argv':a,'extern_files':dep_receipt(st,arg),'outputs':files,'row':row})
            rows.append(row)
    # A cold native configuration deliberately invokes cc and collect2 on conftest inputs that fail.
    assert all(z['exit']==0 or (phase=='cold' and z['role']in ('cc','collect2') and z['exit'] is not None)for z in rows),[(z['role'],z['exit'])for z in rows if z['exit']!=0][:3]
    targets={k:v for k,v in outputs.items() if v['pkg']=='ruff_python_stdlib'}
    matched=[a for a in arts if a['target']['name']==select and a['target']['kind']==['bin']];assert len(matched)==1
    exe=Path(matched[0]['executable']);assert sha(real(exe,st))==outputs[str(exe)]['sha']
    rt={}
    def run(label,args,inp=None):
        rr=subprocess.run(ns+list(map(str,args)),env=env,input=inp,capture_output=True,timeout=60)
        (rec/(label+'.stdout')).write_bytes(rr.stdout);(rec/(label+'.stderr')).write_bytes(rr.stderr)
        rt[label]={'exit':rr.returncode,'stdout_sha':H(rr.stdout),'stderr_sha':H(rr.stderr),'stdout':rr.stdout.decode(errors='replace')[:800],'stderr':rr.stderr.decode(errors='replace')[:400]}
    run('version',[exe,'--version']);assert rt['version']['exit']==0
    for py in ['314','315']:
        if select=='ruff':
            run('behavior'+py,[exe,'check','--isolated','--select','F821','--target-version','py'+py,'--output-format','concise','--stdin-filename','example.py','-'],b'print(__cached__)\n')
            x=rt['behavior'+py]; exp=1 if view=='original'and py=='315'else 0;assert x['exit']==exp and ((b'F821' in (rec/('behavior'+py+'.stdout')).read_bytes())==bool(exp)),x
        else:
            case=rec/'typing.py'
            for b in ['.stdout','.stderr']:
                old=rec/('behavior'+py+b)
                if recover and old.is_file() and not old.with_suffix(b+'.wrong-cli-usage').exists():old.rename(old.with_suffix(b+'.wrong-cli-usage'))
            case.write_text('print(__cached__)\n');run('behavior'+py,[exe,'check','--project',rec,'--python-version','3.'+py[1:],'--output-format','concise',case])
            # Preserve actual semantics in both views and compare against a separately empty same-configuration state.
            assert rt['behavior'+py]['exit']in (0,1),rt['behavior'+py]
    result={'phase':phase,'source':view,'selector':select,'state':state.name,'command':cmd,'cargo_sha256':binding['cargo'],'source_bytes':got,'units':len(arts),'fresh':sum(u['fresh']for u in unit),'physical':dict(collections.Counter(c['role']for c in rows)),'native':rows,'stdlib_outputs':targets,'stdlib_jobs':intern,'cli':{'path':str(exe),'sha':outputs[str(exe)]['sha']},'runtime':rt,'remaining':space(q),'raw_stdout_sha':sha(rec/'stdout'),'raw_stderr_sha':sha(rec/'stderr')}
    assert targets;dump(rec/'products.json',outputs);dump(rec/'units.json',unit);dump(rec/'result.json',result)
    print(state.name,phase,select,len(arts),result['fresh'],result['physical'],len(intern),[rt['behavior'+v]['exit']for v in ('314','315')],flush=True);return result
def init(st):
    st.mkdir(exist_ok=False);(st/'target').mkdir();(st/'shared').mkdir()
    monitored(['cp','-a','--reflink=auto',rp/'graph-registry',st/'registry-home'],repo/(st.name+'-registry.out'),repo/(st.name+'-registry.err'))
def manifests(st):
    by={};inodes={};hashes={};groups=collections.defaultdict(list)
    for cur,dirs,names in os.walk(st):
        for n in sorted(dirs+names):
            f=Path(cur)/n;k=str(f.relative_to(st));s=f.lstat()
            if f.is_symlink():by[k]=['link',os.readlink(f),s.st_mode,s.st_mtime_ns]
            elif f.is_dir():by[k]=['dir',s.st_mode,s.st_mtime_ns]
            elif f.is_file():
                z=(s.st_dev,s.st_ino);inodes[k]=z;groups[z].append(k)
                if z not in hashes:hashes[z]=sha(f)
                by[k]=['file',s.st_size,s.st_mode,s.st_mtime_ns,hashes[z]]
            else:raise AssertionError(k)
    for ns in groups.values():
        for k in ns:by[k].append(min(ns))
    whole=H(b''.join(json.dumps([k,by[k]],separators=(',',':')).encode()+b'\n'for k in sorted(by)))
    return {'sha':whole,'entries':len(by),'files':len(inodes),'unique_bytes':sum(by[min(ns)][1]for ns in groups.values())},inodes
def train(st,view):
    out={}
    for tag in ['cold','settle-1','settle-2','settle-3']:
        vals=[call(st,k,view,tag)for k in ('ruff','ty')]
        if tag!='cold'and all(x['fresh']==x['units']and not x['native']for x in vals):return vals
    raise AssertionError((st,view,'not jointly settled'))
def main():
    phase=sys.argv[1];assert phase in ['seed','R-T','T-R','gold'];stable();guard();seed=tmp/'seed'
    with (p/'native-measure.lock').open('rb')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if phase=='seed':
            if not seed.exists():init(seed)
            else:assert (repo/'seed-cold-ruff/stdout').is_file() and not (repo/'seed-manifest.json').exists()
            train(seed,'original');mm,_=manifests(seed);dump(repo/'seed-manifest.json',mm);return
        st=usr/phase
        if phase=='gold':
            init(st);train(st,'reversed');return
        mm,ino=manifests(seed);assert mm==load(repo/'seed-manifest.json')
        assert not st.exists();size=int(subprocess.check_output(['du','-s','--block-size=1',seed],text=True).split()[0]);assert shutil.disk_usage(usr).free>size+limits[usr]+128*2**20,(size,shutil.disk_usage(usr).free)
        monitored(['cp','-a','--reflink=auto',seed,st],repo/(phase+'-copy.out'),repo/(phase+'-copy.err'))
        nm,other=manifests(st);assert nm==mm and set(ino)==set(other)and all(ino[k]!=other[k]for k in ino);dump(repo/(phase+'-clone.json'),nm)
        order=['ruff','ty']if phase=='R-T'else['ty','ruff']
        for tag,view in [('original','original'),('first-edit','reversed'),('repeat-edit','reversed'),('restore','original'),('repeat-restore','original')]:
            for crate in order:
                v=call(st,crate,view,tag)
                if tag.startswith('repeat')or tag=='original':assert v['fresh']==v['units'] and not v['native'],(phase,tag,crate)
        assert manifests(seed)[0]==mm
if __name__=='__main__':main()
