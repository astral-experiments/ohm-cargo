"""Migrate copies of an official -17 cache whose ordinary executable is already known wrong."""
from pathlib import Path
import hashlib,json,os,re,shutil,socket,subprocess,sys
assert socket.gethostname()=='charlie-ohm-relink-b-1024'
orig=Path('/mnt/devbox-scratch/dev-user/ohm-official-17-foreign-source-audit-20261028');root=Path('/mnt/devbox-scratch/dev-user/ohm-official17-foreign-source-cargo-repair-20261028')
tools=Path('/mnt/devbox-scratch/dev-user/ohm-observer-consumption-tools-20261028')
sdk=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest();get=lambda p:json.loads(p.read_bytes())
put=lambda path,v:path.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def inventory(path):
    return {str(p.relative_to(path)):(['file',p.stat().st_size,p.stat().st_mtime_ns,sha(p)] if p.is_file() else ['symlink',os.readlink(p)]) for p in sorted(path.rglob('*')) if p.is_file() or p.is_symlink()}
def native(x):return subprocess.run([x],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=20)
def run_inside(case,stage,out):
    base=orig/('known-'+case);env=dict(HOME=str(base),PATH=os.environ['PATH'],USER=os.environ['USER'],RUSTUP_HOME=str(base/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(base/'cargo-home'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='2',LANG='C.UTF-8',LC_ALL='C.UTF-8',OHM_SYNC_DIR=str(base))
    env['CARGO_ENCODED_RUSTFLAGS']='--extern\x1fescape_fixture='+str(base/'libescape_fixture.rlib')
    active=base/'warm';target=active/'target';shared=active/'shared-build';env.update(CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared))
    assert Path(subprocess.check_output(['rustc','+ohm','--print=sysroot'],cwd=base/'workspace',env=env,text=True).strip()).samefile(sdk)
    expected=get(root/'binding.json')['cargo']; cargo_sha=sha(sdk/'bin/cargo');assert cargo_sha==expected['stock' if stage=='before' else out.parent.name]
    cmd=['cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json']
    with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
        p=subprocess.run(['strace','-f','-qq','-s','65536','-e','trace=execve','-o',str(out/'exec'),*cmd],cwd=base/'workspace',env=env,stdout=so,stderr=se,timeout=120)
    assert p.returncode==0,(out,(out/'stderr').read_text()[-900:])
    es=[json.loads(l) for l in (out/'stdout').read_bytes().splitlines()];assert es[-1]=={'reason':'build-finished','success':True}
    item,=[e for e in es if e.get('reason')=='compiler-artifact' and e['target']['name']=='hold_direct']
    exe=Path(item['executable']);v=native(exe);assert not v.stderr;(out/'native').write_bytes(v.stdout);value=int(next(l[7:] for l in v.stdout.decode().splitlines() if l.startswith('sample=')))
    fp,=[p for d in (target,shared) for p in d.rglob('dep-bin-hold_direct')];buf=fp.read_bytes();(out/'cargo.fingerprint').write_bytes(buf)
    dep,=[p for d in (target,shared) for p in d.rglob('hold_direct*.d') if p.parent.name=='out' and b'foreign-span' in p.read_bytes()];(out/'rustc.d').write_bytes(dep.read_bytes())
    calls=[]
    for l in (out/'exec').read_text().splitlines():
        if '"--crate-name", "hold_direct"' in l and l.endswith('= 0'):
            m=re.search(r'execve\("([^"]+)"',l)
            if m and Path(m[1]).is_file() and Path(m[1]).samefile(sdk/'bin/rustc'):calls.append(l)
    assert bool(calls)!=item['fresh'],(stage,calls,item['fresh'])
    return dict(value=value,fresh=item['fresh'],compilers=len(calls),full_argv=calls,status=p.returncode,native=v.stdout.decode(),executable=str(exe),elf_sha256=sha(exe),dep_sha256=sha(dep),fp_sha256=sha(fp),wire=buf[5],complete=buf[-41:-37]==b'OBS1' and buf[-33]==1,observed=buf[-41:-37]==b'OBS1',cargo=cargo_sha)
if len(sys.argv)>1 and sys.argv[1]=='inside':
    case,stage,where=sys.argv[2:];out=Path(where);put(out/'result.json',run_inside(case,stage,out));sys.exit()
assert not root.exists() and shutil.disk_usage(root.parent).free>9*2**30;root.mkdir(mode=0o700)
cargo={'stock':sha(sdk/'bin/cargo'),'matched':sha(tools/'matched-cargo'),'fixed':sha(tools/'fixed-cargo')}
assert cargo['stock']=='4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3' and cargo['fixed']=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
rust=sha(sdk/'lib/librustc_driver-b03bf00bec23bb9a.so');assert rust=='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
put(root/'binding.json',dict(cargo=cargo,rust=rust,frontend=sha(sdk/'bin/rustc'),source=sha(Path(__file__)),original_packet='be553f72eae6c0a5e476b895d1eafb3288fe711703521ffd100c925e9eb0323b',plan='two independent copies of each already-poisoned trained state, original -17 command, then matched or corrected Cargo twice, same target and source path; new empty state for each Cargo as independent oracle, no times'))
allrows={}
for stamp in ('current','preserved'):
    base=orig/('known-'+stamp);d=root/stamp;d.mkdir()
    previous=get(base/'complete.json');assert previous['rows']['again']['caller_fresh'] and previous['rows']['again']['value']==17 and previous['rows']['clean']['value']==29
    before=inventory(base/'warm');put(d/'original-inventory.json',before);assert len(before)>15
    for arm in ('matched','fixed'):
        r=d/arm;r.mkdir()
        for kind,name in [('warm','warm'),('cargo-home','cargo-home')]:
            subprocess.run(['cp','-a','--reflink=auto',str(base/kind),str(r/name)],check=True)
        assert inventory(r/'warm')==before and (r/'warm').stat().st_ino!=(base/'warm').stat().st_ino
        (r/'empty').mkdir();results={}
        for stage in ('before','first','second','clean'):
            out=r/stage;out.mkdir();active=r/('empty' if stage=='clean' else 'warm')
            cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(active),str(base/'warm'),'--bind',str(r/'cargo-home'),str(base/'cargo-home'),'--bind',str(out),str(out)]
            if stage!='before':cmd+=['--ro-bind',str(tools/(arm+'-cargo')),str(sdk/'bin/cargo')]
            cmd+=['--','taskset','-c','24-25',sys.executable,'-B',__file__,'inside',stamp,stage,str(out)]
            p=subprocess.run(cmd,capture_output=True,timeout=140);(out/'worker.stderr').write_bytes(p.stderr);assert p.returncode==0,(stamp,arm,stage,p.stderr.decode()[-1000:])
            row=get(out/'result.json');results[stage]=row
            if stage=='before':assert row['fresh'] and row['complete'] and row['value']==17,(stamp,arm,row)
            if stage=='clean':assert row['value']==29 and row['compilers']==1
            print(stamp,arm,stage,row['value'],row['fresh'],row['compilers'],row['complete'],flush=True)
        assert inventory(base/'warm')==before
        allrows[stamp+'-'+arm]=results
    assert sha(base/'foreign.rs')==previous['after']['sha256'] and sha(base/'libescape_fixture.rlib')==previous['external_rlib_sha256']
put(root/'complete.json',allrows)
