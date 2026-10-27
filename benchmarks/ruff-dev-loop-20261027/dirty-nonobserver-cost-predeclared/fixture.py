"""Operate on a complete read-only Ruff checkout with a disposable one-file historical overlay."""
from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,shutil,socket,subprocess,sys,time
P=Path(os.environ['OHM_SCOPED_FIXTURE_ROOT']);I=P/'inputs';S=P/'sdk';root=Path.home()
WT=root/'code/oss/ruff-ohm-frontend-holdout-20261026';src=WT/'crates/ruff_text_size/src/range.rs'
proof=json.loads((I/'preflight-inputs.json').read_bytes());SON='librustc_driver-774a793a844d5500.so';llvm='libLLVM.so.23.1-rust-1.99.0-beta';triple='x86_64-unknown-linux-gnu'
physical=root/'code/oss/ohm-ruff-current-20261021/rustup/toolchains/ohm';driver=Path('/mnt/devbox-scratch/dev-user/ohm-ron-h5-release-20261027-v1/candidate-driver.so')
keys={'B':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','C':'51e2e21a219004007a2d51e19e5a8edc57b47c7eb290383f4bbc13428e0f7d9c'}
def sha(f):
    with Path(f).open('rb') as v:return hashlib.file_digest(v,'sha256').hexdigest()
def scoped(args,work=None):
    return subprocess.run(args,cwd=work or WT,stdin=subprocess.DEVNULL,capture_output=True,env=env)
def check(cp):
    if cp.returncode:raise RuntimeError((cp.returncode,cp.stderr.decode(errors='replace')[-1300:],cp.stdout.decode(errors='replace')[-300:]))
def fresh_flag(s):return s.endswith('-Zohm-observer-dep-info') or s=='ohm-observer-dep-info'
def trace(d):
    jobs=[];probes=[];alltools=[]
    for f in sorted(d.glob('exec.*')):
        pending=None
        for row in f.read_text(errors='replace').splitlines():
            if row.startswith(('execve(','execveat(')) and row.endswith('<unfinished ...>'):pending=row.removesuffix('<unfinished ...>');continue
            m=re.match(r'^<\.\.\. (?:execve|execveat) resumed>(.*)$',row)
            if m:assert pending;row,pending=pending+m[1],None
            if not re.search(r'\)\s+= 0$',row) or not row.startswith(('execve(','execveat(')):continue
            m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',row);assert m,row[:140]
            exe=ast.literal_eval(m[1]);a=[ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])];name=Path(exe).name;alltools.append(name)
            if name=='rustc' and '--crate-name' in a and not any(k.startswith('--print=') for k in a):
                jobs.append({'crate':a[a.index('--crate-name')+1],'depinfo_flag':any(map(fresh_flag,a)),'emit':next(k for k in a if k.startswith('--emit')),'argv_sha256':hashlib.sha256(json.dumps(a).encode()).hexdigest()})
            if name=='rustc' and '--print=sysroot' in a and any(map(fresh_flag,a)):probes.append(f.name)
        assert pending is None
    return {'jobs':jobs,'observer_probes':len(probes),'executable_basename_counts':collections.Counter(alltools)}
def scope(state,arm):
    return ['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--bind',P,P,'--tmpfs','/tmp',
            '--bind',state/'target',P/'canonical/target','--bind',state/'build',P/'canonical/build','--bind',state/'home',P/'canonical/home',
            '--ro-bind',state/'payload',src,'--ro-bind',I/arm,S/'bin/cargo','--ro-bind',driver,S/'lib'/SON,'--ro-bind',physical/'lib'/llvm,S/'lib'/llvm,'--chdir',WT,'--',
            'taskset','-c','8-11']
def cargo_command(kind):return ['cargo','+ohm',kind,'--locked','--offline','-p','ruff_text_size','--message-format=json']
def archive(path):
    names=subprocess.check_output(['/usr/bin/ar','t',path]).decode().splitlines()
    assert len(names)==len(set(names)) and names and all('/' not in x for x in names)
    def digest(b):return hashlib.sha256(b).hexdigest()
    files=[(name,subprocess.check_output(['/usr/bin/ar','p',path,name])) for name in names]
    cgus=[n for n,raw in files if n.endswith('.rcgu.o')];assert cgus
    out=[]
    for name,raw in files:
        # Keep every original name and raw byte commitment. The native proof below must
        # still compare full ELF codegen unit bytes across independent arm builds.
        normalized=raw
        if name in ('lib.rmeta','lib.rmeta-link'):
            for j,ref in enumerate(cgus):
                normalized=normalized.replace(ref.encode(),('member-%03d'%j).encode())
        kind='codegen' if name in cgus else name
        out.append({'label':name,'kind':kind,'size':len(raw),'sha':digest(raw),'exact_member_names_folded':digest(normalized)})
    return out
def api(state,arm,kind,art,is_edited,d):
    filename=next(n for n in art['filenames'] if n.endswith('.rmeta' if kind=='check' else '.rlib'))
    out=d/('caller.rmeta' if kind=='check' else 'caller')
    opt=['--emit=metadata'] if kind=='check' else []
    cp=scoped([*scope(state,arm),'rustc','+ohm','--edition=2024',I/'caller.rs','--extern','ruff_text_size='+filename,*opt,'-o',out])
    if is_edited:
        assert cp.returncode==1 and b'E0599' in cp.stderr and b'to_std_range' in cp.stderr,cp.stderr[-260:]
        return {'rc':1,'code':'E0599'}
    check(cp)
    if kind=='check':assert out.is_file();return {'rc':0,'metadata':True}
    run=scoped([*scope(state,arm),out]);check(run);assert run.stdout.strip()==b'2-6';return {'rc':0,'ordinary_output':'2-6'}
def state_dir(kind,arm):
    st=P/'states'/(kind+'-'+arm);return st
def init_state(arm,kind):
    st=state_dir(kind,arm);st.mkdir(parents=True);(st/'target').mkdir();(st/'build').mkdir();(st/'home').mkdir()
    namespace=(I/'cache-namespace').read_text().strip();assert Path(namespace).name==namespace and namespace not in ('.','..')
    reg=st/'home/registry/index'/namespace;reg.parent.mkdir(parents=True);shutil.copytree(I/'index',reg)
    (reg/'config.json').write_text('{"dl":"https://static.crates.io/crates","api":"https://crates.io"}\n');(st/'payload').write_bytes((I/'range.rs').read_bytes());return st
def source(st,edited):
    path=I/('edited.rs' if edited else 'range.rs');assert sha(path)==proof['edited_file_sha256' if edited else 'original_file_sha256'];f=st/'payload';f.write_bytes(path.read_bytes());os.utime(f,None)
def observe(st,kind,arm,phase,edited=True,traced=True):
    d=P/'records'/(kind+'-'+arm)/phase;d.mkdir(parents=True)
    log=['strace','-ff','-qq','-s','32768','-e','trace=execve,execveat','-o',d/'exec'] if traced else []
    if not traced:log=['/usr/bin/python3','-B',I/'inside.py',d/'elapsed-ns']
    cp=scoped([*scope(st,arm),*log,*cargo_command(kind)]);check(cp)
    rows=[json.loads(l) for l in cp.stdout.splitlines() if l];assert rows[-1]=={'reason':'build-finished','success':True}
    arts=[z for z in rows if z.get('reason')=='compiler-artifact'];hit,=[z for z in arts if z['target']['name']=='ruff_text_size']
    assert len(arts)==1 and not [z for z in rows if z.get('reason')=='compiler-message'],(len(arts),cp.stderr[-270:])
    sigs={};members=None
    for name in hit['filenames']:
        rel=Path(name).relative_to(P/'canonical');assert rel.parts[0] in ('target','build')
        f=st/rel;sigs[f.suffix]=sha(f)
        if f.suffix=='.rlib':members=archive(f)
    deps=[f for part in ('target','build') for f in (st/part).rglob('ruff_text_size-*.d') if f.is_file()]
    assert deps and all((x.read_bytes()==deps[0].read_bytes()) for x in deps),deps
    dep=deps[0];deps_txt=dep.read_text();checksum_rows=sum(s.startswith('# checksum:') for s in deps_txt.splitlines());marker='ohm-foreign-span' in deps_txt;assert not marker,(kind,arm,phase,checksum_rows,marker)
    rr=dict(units=len(arts),members=members,checksummed_sources=checksum_rows,foreign_marker=marker,fresh=hit['fresh'],depinfo_sha256=sha(dep),outputs=sigs,ordinary_api=api(st,arm,kind,hit,edited,d),source=sha(st/'payload'),trace=trace(d) if traced else None)
    if traced:print(kind,arm,phase,'fresh',rr['fresh'],'compiled',len(rr['trace']['jobs']),'queries',rr['trace']['observer_probes'],'external_marker',marker,'checksums',checksum_rows,file=sys.stderr,flush=True)
    if not traced:rr['elapsed_ns']=int((d/'elapsed-ns').read_text());assert rr['elapsed_ns']>0
    return rr
def prepare():
    assert set(range(8,12))<=os.sched_getaffinity(0) and os.uname().nodename=='charlie-ohm-mono-bench' and not (P/'records').exists()
    assert shutil.disk_usage(P).free>8*2**30 and shutil.disk_usage('/mnt/devbox-scratch').free>2**30
    for k,v in keys.items():assert sha(I/k)==v
    assert sha(driver)=='185629fabec9baacfd8fd7e61d6d84e79f69aa9abf4a4a9bb431c24f0a89d040' and sha(physical/'lib'/llvm)=='43bac9749e539cd5988a4d5452b64582cf07ac9e7c059fde29c7bee76e106c51'
    assert sha(S/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f' and sha(S/'lib/rustlib'/triple/'lib/libstd-150b24506f9fb8c9.rlib')=='bb1da52e02b3bf34996fb9bc50c6d80b9244a23b8fe6d3b47f7eabd5953d4191'
    assert sha(S/'lib/rustlib'/triple/'bin/wild-ld/ld.bfd')=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'; (S/'bin/cargo').touch();(S/'lib'/SON).touch();(S/'lib'/llvm).touch()
    for n in ['target','build','home']:(P/'canonical'/n).mkdir(parents=True)
    (P/'rustup/toolchains').mkdir(parents=True);(P/'rustup/toolchains/ohm').symlink_to(S,target_is_directory=True)
    (P/'rustup/settings.toml').write_text('version = "12"\nprofile = "minimal"\n');(P/'tmp').mkdir();(P/'home').mkdir()
    assert subprocess.check_output(['git','--no-optional-locks','-C',WT,'rev-parse','HEAD']).decode().strip()==proof['ruff'] and not subprocess.check_output(['git','--no-optional-locks','-C',WT,'status','--porcelain'])
    assert sha(src)==proof['original_file_sha256']
env={'HOME':str(P/'home'),'USER':os.environ['USER'],'PATH':str(root/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin','RUSTUP_HOME':str(P/'rustup'),'RUSTUP_AUTO_INSTALL':'0','CARGO_HOME':str(P/'canonical/home'),'CARGO_TARGET_DIR':str(P/'canonical/target'),'CARGO_BUILD_BUILD_DIR':str(P/'canonical/build'),'CARGO_BUILD_JOBS':'4','CARGO_TERM_COLOR':'never','LC_ALL':'C.UTF-8','TMPDIR':str(P/'tmp'),'GIT_OPTIONAL_LOCKS':'0'}
def qualify():
    res={}
    for kind in ('check','build'):
        for arm in ('B','C','B2','C2'):
            compiler=arm[:1]
            st=init_state(arm,kind);records={}
            for ph,edited,write in [('original',False,False),('edit',True,True),('unchanged_edit',True,False),('restore',False,True),('unchanged_restore',False,False)]:
                if write:source(st,edited)
                row=observe(st,kind,compiler,ph+'-'+arm,edited);assert row['fresh']==(not write and ph!='original')
                assert len(row['trace']['jobs'])==(0 if row['fresh'] else 1) and all(a['crate']=='ruff_text_size' for a in row['trace']['jobs'])
                records[ph]=row
            res[kind+'-'+arm]=records
    assert shutil.disk_usage(P).free>6*2**30
    for kind in ('check','build'):
        a,b=res[kind+'-B'],res[kind+'-C']
        assert all(a[phase]['ordinary_api']==b[phase]['ordinary_api'] for phase in a)
    return dict(subjects=keys,driver=sha(driver),git=proof,qualified=res,temporary_byte_size=sum(x.stat().st_size for x in P.rglob('*') if x.is_file() and not x.is_symlink()))
if __name__=='__main__':
    with (root/'.cache/ohm-hillclimb-release.lock').open('r') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        prepare();x=qualify();assert x['temporary_byte_size']<2**30;print(json.dumps(x,separators=(',',':')),flush=True)
