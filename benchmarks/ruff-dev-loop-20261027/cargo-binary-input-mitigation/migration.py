"""Reopen an actual previously wrong target at identical paths and switch only its Cargo executable."""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,subprocess,sys,traceback
here=Path(__file__).resolve().parent
bank=Path('/dev/shm/ohm-observer-protocol-h1-20261027/optional-native-pilot1-20261028')
tools=Path('/mnt/devbox-scratch/dev-user/ohm-observer-consumption-tools-20261028');fix=tools/'fixed-cargo'
storage=Path('/dev/shm/ohm-previously-wrong-binary-migrations-h1-20261028-v1');storage.mkdir(mode=0o700)
save=here/'receipts';save.mkdir(mode=0o700)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
J=lambda f:json.loads(f.read_bytes())
def put(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def tree(p):
    h=hashlib.sha256();n=0
    for f in sorted(p.rglob('*')):
        if f.is_symlink():
            data=os.readlink(f)
        elif f.is_file():data=sha(f)
        else:continue
        s=f.lstat();key=[str(f.relative_to(p)),data,s.st_mode,s.st_size,s.st_mtime_ns]
        h.update(json.dumps(key).encode()+b'\n');n+=1
    return {'files':n,'sha256':h.hexdigest()}
def run(case,kind,origin,stamp):
    known=origin=='known';key='-'.join([kind,origin,stamp])
    site={'dso':('same-metadata-dso-h1-20261028-v2','trained-same-metadata-dso-h1-20261028-v3'),'rmeta':('column-rmeta-h1-20261028-v4','trained-column-rmeta-h1-20261028-v5')}[kind][known]
    src=Path('/dev/shm')/('ohm-synchronized-'+site)/('released-sources' if known else 'candidate')/(kind+'-'+stamp)
    keep=storage/key;keep.mkdir();sd=save/key;sd.mkdir()
    old=bank/'pinned-subjects'/('A' if known else 'N')/'cargo';sdk=bank/('N-old-raw' if known else 'N-common')/'active-sdk'
    idn={'old':sha(old),'fixed':sha(fix),'driver':sha(sdk/'lib/librustc_driver-774a793a844d5500.so'),'frontend':sha(sdk/'bin/rustc')};assert idn['fixed']=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
    oldcase=J(src/'complete.json');donor=src/'warm';before=tree(donor)
    assert oldcase['rows']['again']['exit']==0 and oldcase['rows']['again']['unit_fresh'] is True
    assert oldcase['rows']['again']['value']==(17 if kind=='dso' else None)
    for n in ('warm','cargo-home'):
        subprocess.run(['cp','-a','--reflink=auto',str(src/n),str(keep/n)],check=True)
    (keep/'clean').mkdir()
    assert tree(keep/'warm')==before
    unit,=[f for f in donor.rglob('dep-bin-hold_direct') if f.is_file()];proof=unit.read_bytes()
    assert proof[-41:-37]==b'OBS1' and proof[-33]==1
    assert (oldcase['rows']['again']['claims']['cargo_fingerprint']==sha(unit))
    outer=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--bind',str(keep),str(keep),'--bind',str(keep/'cargo-home'),str(src/'cargo-home'),'--tmpfs','/tmp']
    env={'HOME':str(src),'PATH':os.environ['PATH'],'USER':os.environ.get('USER','dev-user'),'RUSTUP_HOME':str(src/'rustup'),'RUSTUP_AUTO_INSTALL':'0','CARGO_HOME':str(src/'cargo-home'),'CARGO_BUILD_JOBS':'4','OHM_SYNC_DIR':str(src),'CARGO_NET_OFFLINE':'true','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','CARGO_TARGET_DIR':str(donor/'target'),'CARGO_BUILD_BUILD_DIR':str(donor/'shared'),'CARGO_ENCODED_RUSTFLAGS':'--extern\x1frace_extern='+str(src/'inputs'/('librace_extern.'+('so' if kind=='dso' else 'rmeta')))}
    if known:env['OHM_SYNC_CONSTANT']='fixed'
    outcomes={}
    for phase in ['old-confirm','fixed-one','fixed-two','fixed-clean']:
        dest=keep/phase;dest.mkdir();subject=old if phase=='old-confirm' else fix;state=keep/('clean' if phase=='fixed-clean' else 'warm');arg=[*outer,'--bind',str(state),str(donor),'--ro-bind',str(subject),str(sdk/'bin/cargo'),'--','taskset','-c','12-15','strace','-ff','-qq','-s','65535','-e','trace=execve','-o',str(dest/'exec'),'cargo','+ohm','build' if kind=='dso' else 'check','-p','hold_direct','--offline','--message-format=json']
        with (dest/'stdout').open('xb') as so,(dest/'stderr').open('xb') as se:q=subprocess.run(arg,cwd=src/'workspace',env=env,stdout=so,stderr=se,timeout=120)
        ev=[json.loads(x) for x in (dest/'stdout').read_bytes().splitlines()];assert ev[-1]=={'reason':'build-finished','success':q.returncode==0}
        aa=[v for v in ev if v['reason']=='compiler-artifact' and v['target']['name']=='hold_direct'];diag=[{'code':(v['message'].get('code') or {}).get('code'),'message':v['message']['message']} for v in ev if v['reason']=='compiler-message' and v['message']['level']=='error']
        native=[];traces={}
        for f in sorted(dest.glob('exec.*')):
            traces[f.name]=sha(f)
            for line in f.read_text().splitlines():
                if not line.startswith('execve(') or not line.endswith(' = 0'):continue
                m=re.match(r'execve\(("[^"]+"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line)
                if not m:continue
                image=Path(ast.literal_eval(m[1]));av=ast.literal_eval(m[2])
                if image.name=='rustc' and '--crate-name' in av:native.append({'rustc':av[av.index('--crate-name')+1],'binary_dep_info':'-Zbinary-dep-depinfo' in av,'blake3':'-Zchecksum-hash-algorithm=blake3' in av})
                if image.name=='ld.bfd':native.append({'wild':True})
        value=None;fresh=aa[0]['fresh'] if len(aa)==1 else None
        if kind=='dso' and q.returncode==0:
            primary,=aa;logical=Path(primary['executable']);real=state/logical.relative_to(donor);runexe=subprocess.run([real],capture_output=True,check=True)
            assert not runexe.stderr;value=int(re.search(rb'(?m)^sample=(\d+)$',runexe.stdout)[1]);assert value in (17,29)
        fp=[p for p in state.rglob('dep-bin-hold_direct') if p.is_file()]
        entry=dict(exit=q.returncode,value=value,fresh=fresh,diagnostics=diag,native=native,traces=traces,stdout_sha=sha(dest/'stdout'),stderr_sha=sha(dest/'stderr'),fingerprints=[sha(f) for f in fp])
        outcomes[phase]=entry;put(sd/(phase+'.json'),entry)
    assert outcomes['old-confirm']['fresh'] and outcomes['old-confirm']['exit']==0 and not outcomes['old-confirm']['native'] and outcomes['old-confirm']['value']==(17 if kind=='dso' else None)
    assert tree(donor)==before
    result={'source_scenario':key,'base_subjects':idn,'genuine_wrong_proof_sha256':sha(unit),'private_tree_before_and_after':before,'rows':outcomes}
    put(sd/'complete.json',result);return result
try:
    allr={}
    for case in [('dso','known'),('rmeta','known'),('dso','first'),('rmeta','first')]:
        for stamp in ('current','preserved'):
            assert shutil.disk_usage(storage).free>1.5*2**30
            k='-'.join((*case,stamp));r=run(k,*case,stamp);allr[k]=r;print(k,[(key,v['exit'],v['value'],v['fresh'],[c['code'] for c in v['diagnostics']]) for key,v in r['rows'].items()],flush=True)
    put(save/'complete.json',allr)
except BaseException:
    (save/'failure.txt').write_text(traceback.format_exc());raise
