"""Run an ordinary Cargo binary with an external writer between macro expansion and dep-info."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,time
inputs=Path(__file__).resolve().parent
sdk=Path(sys.argv[1]); root=Path(sys.argv[2]); kind,stamp,training=sys.argv[3:];root.mkdir()
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
put=lambda path,value:path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
work=root/'workspace';shutil.copytree(inputs/'fixture',work)
home=root/'rustup';(home/'toolchains').mkdir(parents=True);(home/'toolchains/ohm').symlink_to(sdk)
env=dict(HOME=str(root),PATH=os.environ['PATH'],USER=os.environ['USER'],RUSTUP_HOME=str(home),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(root/'cargo-home'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='2',LANG='C.UTF-8',LC_ALL='C.UTF-8',OHM_SYNC_DIR=str(root))
def run(args):return subprocess.run(args,env=env,cwd=work,capture_output=True,timeout=90,check=True)
assert Path(run(['rustc','+ohm','--print','sysroot']).stdout.decode().strip()).samefile(sdk)
external=root/'libescape_fixture.rlib';source=root/'foreign.rs';contents=b'#[macro_export]\nmacro_rules! sampled { ($gate:ident) => { $gate!(foreign_marker) }; }\n// private note 17\n'
source.write_bytes(contents)
run(['rustc','+ohm','--crate-name','escape_fixture','--crate-type','rlib','-Cmetadata=static-tag','-Cdebuginfo=0',str(source),'-o',str(external)])
env['CARGO_ENCODED_RUSTFLAGS']='--extern\x1fescape_fixture='+str(external)
payload=root/'private-input.txt';payload.write_bytes(b'17')
if kind=='foreign-text':
    probe=work/'hold_probe/src/lib.rs'
    probe.write_text(probe.read_text()+'''
#[proc_macro]
pub fn foreign_text(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let text = input.into_iter().next().unwrap().span().source_text();
    let value = match text.as_deref() { Some("foreign_marker") => "17", None => "29", _ => panic!("unexpected source text: {text:?}") };
    wait_value(value.parse().unwrap())
}
''')
    pre='use hold_probe::foreign_text;'; gate='escape_fixture::sampled!(foreign_text)';observed=source;replacement=contents.replace(b'note 17',b'note 29')
else:
    assert kind=='tracked-path'
    pre='use hold_probe::wait_value;';gate='wait_value!(file)';observed=payload;replacement=b'29'
main=work/'hold_direct/src/main.rs';orig=main.read_text();assert orig.count('fn main(){')==1
main.write_text(pre+'\n'+orig.replace('fn main(){','fn main(){println!("sample={}",'+gate+');'))
def stat(p):
    s=p.stat();return dict(bytes=s.st_size,inode=s.st_ino,mtime_ns=s.st_mtime_ns,sha256=sha(p))
before=stat(observed);rows={};seeds={}
assert training in ('first','known')
if training=='known':
    target=root/'warm/target';shared=root/'warm/shared-build';env.update(CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared))
    for tag in ('seed','learn','stable'):
        rd=root/tag;rd.mkdir();cmd=['cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json']
        proc=run(['strace','-f','-qq','-s','65536','-e','trace=execve','-o',str(rd/'exec'),*cmd]);(rd/'stdout').write_bytes(proc.stdout);(rd/'stderr').write_bytes(proc.stderr)
        es=[json.loads(l) for l in proc.stdout.splitlines()];item,=[v for v in es if v.get('reason')=='compiler-artifact' and v['target']['name']=='hold_direct'];out=run([item['executable']]).stdout;assert b'sample=17\n' in out
        fp,=[p for d in [target,shared] for p in d.rglob('dep-bin-hold_direct')];data=fp.read_bytes();(rd/'cargo.fingerprint').write_bytes(data);(rd/'native').write_bytes(out)
        seeds[tag]=dict(value=17,fresh=item['fresh'],status=proc.returncode,claim_complete=data[-41:-37]==b'OBS1' and data[-33]==1)
    assert seeds['stable']['fresh'] and seeds['stable']['claim_complete'],seeds
    original=main.read_bytes();main.write_bytes(original+b'\nconst _: usize = core::mem::size_of::<u32>();\n')
    put(root/'training.json',dict(rows=seeds,pre=hashlib.sha256(original).hexdigest(),post=sha(main)))
(root/'armed').touch()
for phase in ['initial','repeat','again','clean']:
    state=root/('empty' if phase=='clean' else 'warm');target=state/'target';shared=state/'shared-build';env.update(CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared))
    rd=root/phase;rd.mkdir()
    cmd=['cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json']
    with (rd/'stdout').open('xb') as so,(rd/'stderr').open('xb') as se:
        child=subprocess.Popen(['strace','-f','-qq','-s','65536','-e','trace=execve','-o',str(rd/'exec'),*cmd],env=env,cwd=work,stdout=so,stderr=se)
        if phase=='initial':
            limit=time.monotonic()+65
            while not (root/'observed').is_file() and child.poll() is None and time.monotonic()<limit:time.sleep(.01)
            assert (root/'observed').read_text().strip()=='17'
            swap=observed.with_name(observed.name+'.replacement');swap.write_bytes(replacement)
            if stamp=='preserved':os.utime(swap,ns=(observed.stat().st_atime_ns,before['mtime_ns']))
            os.replace(swap,observed);after=stat(observed)
            assert before['bytes']==after['bytes'] and before['sha256']!=after['sha256'] and before['inode']!=after['inode']
            assert after['mtime_ns']==before['mtime_ns'] if stamp=='preserved' else after['mtime_ns']>before['mtime_ns']
            (root/'release').touch();(root/'armed').unlink()
        rc=child.wait(timeout=90);assert rc==0,(phase,rc,(rd/'stderr').read_text()[-1200:])
    events=[json.loads(l) for l in (rd/'stdout').read_bytes().splitlines()]
    assert events[-1]=={'reason':'build-finished','success':True};row,=[x for x in events if x.get('reason')=='compiler-artifact' and x['target']['name']=='hold_direct']
    exe=Path(row['executable']);ret=run([exe]);assert not ret.stderr;(rd/'native').write_bytes(ret.stdout)
    value=int(next(l[7:] for l in ret.stdout.decode().splitlines() if l.startswith('sample=')))
    places=[target,shared];dep,=[p for d in places for p in d.rglob('hold_direct*.d') if p.parent.name=='out' and b'foreign-span' in p.read_bytes()]
    fp,=[p for d in places for p in d.rglob('dep-bin-hold_direct')];raw=dep.read_bytes();binary=fp.read_bytes();(rd/'rustc.d').write_bytes(raw);(rd/'cargo.fingerprint').write_bytes(binary)
    hdr=[l for l in raw.splitlines() if l.startswith(b'# ohm-observer-inputs-v1 ')];assert len(hdr)<=1;full=bytes.fromhex(hdr[0].split()[3].decode()) if hdr else raw
    traces=[line for line in (rd/'exec').read_text().splitlines() if 'execve("'+str(sdk/'bin/rustc')+'"' in line and '"--crate-name", "hold_direct"' in line and line.endswith('= 0')]
    rows[phase]=dict(value=value,caller_fresh=row['fresh'],full_calls=len(traces),elf_sha256=sha(exe),dep_sha256=sha(dep),fingerprint_sha256=sha(fp),wire=binary[5],observer_trailer=(binary[-41:-37]==b'OBS1'),claim_complete=binary[-41:-37]==b'OBS1' and binary[-33]==1,untrackable=b'ohm-untrackable-foreign-span' in raw,observer=b'ohm-foreign-span-bytes' in raw,optional=bool(hdr),input_checksum=[v.decode() for v in full.splitlines() if v.startswith(b'# checksum:') and v.endswith(os.fsencode(observed))],stdio=ret.stdout.decode(),status=rc)
    put(rd/'result.json',rows[phase])
assert rows['initial']['value']==17 and rows['clean']['value']==29 and stat(observed)==after
put(root/'complete.json',dict(kind=kind,stamp=stamp,training=training,seeds=seeds,before=before,after=after,external_rlib_sha256=sha(external),argv=cmd,rows=rows))
print([(p,r['value'],r['caller_fresh'],r['claim_complete'],r['untrackable']) for p,r in rows.items()],flush=True)
