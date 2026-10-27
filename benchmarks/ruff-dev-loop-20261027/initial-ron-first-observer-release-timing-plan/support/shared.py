"""Registered paths and independent writable histories of the three native Cargo arms."""
from pathlib import Path
import hashlib,json,os,shutil,socket,stat,subprocess
P=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');WT=Path('/home/dev-user/code/oss/ruff-ohm-empty-test-h4-20261027')
HERE=Path(__file__).resolve().parent; FROZEN=P/'frozen-toolchain';TARGET=P/'native-target';BUILD=P/'shared';CH=P/'registry-home';TRANSFER=P/'transfer'
SONAME='librustc_driver-774a793a844d5500.so';FRONT='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
PLAN_SHA='ce588a79d26e8088bf47a9e85d1e6e5ad357de1745fd98c8d1c6b0d7bcaeeb0c'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def need(yes,why):
    if not yes:raise RuntimeError(why)
def env():
    h=Path.home();return {'HOME':str(h),'USER':os.environ['USER'],'LOGNAME':os.environ.get('LOGNAME',os.environ['USER']),'PATH':f'{h}/.cargo/bin:{h}/.local/bin:/usr/local/bin:/usr/bin:/bin','CARGO_HOME':str(CH),'RUSTUP_HOME':str(P/'rustup'),'RUSTUP_AUTO_INSTALL':'0','CARGO_TARGET_DIR':str(TARGET),'CARGO_BUILD_BUILD_DIR':str(BUILD),'CARGO_BUILD_JOBS':'8','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST':'all','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST':'all','GIT_OPTIONAL_LOCKS':'0','LC_ALL':'C.UTF-8','CARGO_TERM_COLOR':'never','SSL_CERT_FILE':'/etc/ssl/certs/ca-certificates.crt','SSL_CERT_DIR':'/etc/ssl/certs'}
def git(*args):return subprocess.check_output(['git','--no-optional-locks','-C',WT,*args],env=env()).strip()
def floors(extra=0):
    v=[shutil.disk_usage(p).free for p in (P,Path.home())];need(v[0]>25*2**30+extra and v[1]>25*2**30,('25-GiB reserve',v,extra));return v
def plan():
    need(socket.gethostname()=='charlie-ohm-generic-perf-1024' and __debug__,'wrong host / optimized verifier')
    need(sha(TRANSFER/'fixed-width-plan.json')==PLAN_SHA,'registered plan');return load(TRANSFER/'fixed-width-plan.json')
def fixture(edit):
    desc=plan()['edits'][edit];f=P/'fixtures'/edit
    if f.exists():need((f/'manifest.json').is_file(),'unfinished fixture');return f
    need(sha(TRANSFER/(edit+'.patch'))==desc['patch_sha256'] and git('rev-parse','HEAD').decode()==plan()['pin'] and not git('status','--porcelain'),'frozen git')
    a=f/'original';b=f/'edited';a.mkdir(parents=True)
    for rel in desc['paths']:
        dst=a/rel;dst.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(WT/rel,dst)
    shutil.copytree(a,b)
    for flags in [['--check'],['--whitespace=nowarn']]:
        subprocess.run(['git','apply','--no-index','--reverse',*flags,str(TRANSFER/(edit+'.patch'))],cwd=b,env=env(),check=True)
    mf={tag:{p:sha(d/p) if (d/p).is_file() else None for p in desc['paths']} for tag,d in [('original',a),('edited',b)]}
    need(all(mf['original'][p]!=mf['edited'][p] for p in desc['paths']),'complete reverse edit')
    dump(f/'manifest.json',mf);return f
def state(edit,arm):return P/'states'/edit/arm
def srcbinds(f):
    mf=load(f/'manifest.json');parents={Path(p).parent for p,h in mf['edited'].items() if h is None}
    return sorted(parents|{Path(p) for p in mf['original'] if not any(q in Path(p).parents for q in parents)})
def mark(st,f,edited):
    label='edited' if edited else 'original';tag=st/'source-state';mf=load(f/'manifest.json')
    if tag.is_file() and tag.read_text()==label:return
    for rel,v in mf[label].items():
        d=st/'inputs'/rel;r=f/label/rel
        if v:d.write_bytes(r.read_bytes());os.chmod(d,r.stat().st_mode&0o777);need(sha(d)==v,('source',rel))
        elif d.exists():d.unlink()
    tag.write_text(label)
def seed(edit,arm):
    st=state(edit,arm);f=fixture(edit);floors(15*2**30);need(not st.exists(),('state exists',st));st.mkdir(parents=True,mode=0o700)
    for n in ('target','build','home','inputs'):(st/n).mkdir(mode=0o700)
    shutil.copytree(P/'rustup',st/'rustup',symlinks=True)
    subprocess.run(['cp','-a','--reflink=auto','--',str(CH/'registry'),str(st/'home/registry')],check=True)
    for name in ['config','config.toml']:
        if (CH/name).is_file():shutil.copy2(CH/name,st/'home'/name)
    for r in srcbinds(f):
        d=st/'inputs'/r;d.parent.mkdir(parents=True,exist_ok=True)
        if (WT/r).is_dir():shutil.copytree(WT/r,d)
        else:shutil.copy2(WT/r,d)
    mark(st,f,False);need(not any((st/'target').iterdir()) and not any((st/'build').iterdir()),'dirty initial state')
    dump(st/'seed.json',{'empty_target':True,'empty_shared':True,'registry_input_only':True,'device':st.stat().st_dev,'free':floors()})
def view(edit,edited):
    mf=load(P/'fixtures'/edit/'manifest.json');tag='edited' if edited else 'original'
    for rel,h in mf[tag].items():
        p=WT/rel;need((sha(p) if p.is_file() else None)==h,('source overlay',edit,tag,rel))
    changed=git('diff','--name-status','--no-ext-diff','--',*mf[tag]).decode().splitlines()
    expected=sorted((('M' if h is not None else 'D')+'\t'+name) for name,h in mf[tag].items()) if edited else []
    need(sorted(changed)==expected,('source changes',changed,expected))
def skeleton(where):
    root=where/'secure-root'; saved=where/'secure-options.json'
    if saved.is_file():return load(saved)
    root.mkdir(mode=0o700); branches=set(CH.parents); mounts=[]
    def populate(orig,dest):
        for src in sorted(orig.iterdir()):
            out=dest/src.name;mode=src.lstat().st_mode
            if stat.S_ISLNK(mode):out.symlink_to(os.readlink(src));continue
            if stat.S_ISDIR(mode):out.mkdir(mode=0o700)
            elif stat.S_ISREG(mode):out.touch()
            else:continue
            if src==root:continue
            if src in branches:populate(src,out)
            elif src==Path('/proc'):mounts.extend(['--proc','/proc'])
            elif src==Path('/dev'):mounts.extend(['--dev-bind','/dev','/dev'])
            elif src==Path('/tmp'):mounts.extend(['--bind','/tmp','/tmp'])
            elif src in {CH,TARGET,BUILD}: pass
            else:mounts.extend(['--ro-bind',str(src),str(src)])
    populate(Path('/'),root)
    args=['bwrap','--ro-bind',str(root),'/',*mounts];dump(saved,args);return args


def shell(edit,arm):
    st=state(edit,arm);opts=skeleton(st)
    for s,d in [(P/'results',P/'results'),(st/'target',TARGET),(st/'build',BUILD),(st/'home',CH),(st/'rustup',P/'rustup')]:
        opts+=['--bind',str(s),str(d)]
    for s,d in [(TRANSFER/arm,FROZEN/'bin/cargo'),(TRANSFER/'rustc-driver',FROZEN/'lib'/SONAME),*[(st/'inputs'/r,WT/r) for r in srcbinds(P/'fixtures'/edit)]]:
        opts+=['--ro-bind',str(s),str(d)]
    return [*opts,'--','taskset','-c','0-23']
def trusted():
    for p in [CH,*CH.parents]:
        s=p.lstat();need(not p.is_symlink() and p.is_dir() and s.st_uid in {os.getuid(),0} and not (s.st_mode&0o022),('unsafe registry ancestor',p,oct(s.st_mode)))
