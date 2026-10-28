"""Replace an observed input after its bytes are consumed and before rustc writes dep-info."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

H=Path(__file__).resolve().parent

def digest(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def stable(p):
    s=p.stat();return dict(inode=s.st_ino,size=s.st_size,mtime=s.st_mtime_ns,sha256=digest(p))

def run_case(root,sdk,kind,stamp):
    root.mkdir(); work=root/'workspace'; shutil.copytree(H/'fixture',work)
    rustup=root/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(sdk)
    env=dict(HOME=str(root),PATH=os.environ['PATH'],USER=os.environ.get('USER','dev-user'),RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(root/'cargo-home'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='4',OHM_SYNC_DIR=str(root),LANG='C.UTF-8',LC_ALL='C.UTF-8')
    def run(args):return subprocess.run(args,env=env,cwd=work,capture_output=True,check=True,timeout=120)
    assert Path(run(['rustc','+ohm','--print','sysroot']).stdout.decode().strip()).samefile(sdk)
    chan=root/'control';chan.mkdir(); ext=chan/'libescape_fixture.rlib';payload=root/'private-input.txt';payload.write_text('17');alt=root/'later.rlib';source=root/'fixed.rs';rlib=root/'libescape_fixture.rlib'
    for value,dest in [(17,ext),(29,alt)]:
        source.write_text('#[macro_export]\nmacro_rules! sampled { ($gate:ident) => { $gate!('+str(value)+') }; }\n');run(['rustc','+ohm','--crate-type','rlib','--crate-name','escape_fixture','-Cmetadata=static-tag','-Cdebuginfo=0',str(source),'-o',str(rlib)]);shutil.copyfile(rlib,dest)
    # Make tooling and the captured measurement independent of a dependency's optimization stage.
    env['CARGO_ENCODED_RUSTFLAGS']='--extern\x1fescape_fixture='+str(ext)
    main=work/'hold_direct/src/main.rs';code=main.read_text();assert code.count('fn main(){')==1
    gate='escape_fixture::sampled!(wait_value)' if kind=='external-rlib' else 'wait_value!(file)'
    main.write_text('use hold_probe::wait_value;\n'+code.replace('fn main(){','fn main(){println!("sample={}",'+gate+');'))
    real=ext if kind=='external-rlib' else payload
    (root/'armed').write_text('1');before=stable(real); assert real.stat().st_size==alt.stat().st_size if kind=='external-rlib' else True
    rows={}
    for stage in ('initial','repeat','again','clean'):
        place=root/('independent' if stage=='clean' else 'warm');target=place/'target';shared=place/'shared-build';env.update(CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared));rec=root/stage;rec.mkdir()
        args=['cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json'];argv=['strace','-f','-qq','-s','65535','-e','trace=execve','-o',str(rec/'exec'),*args]
        with (rec/'stdout').open('wb') as so,(rec/'stderr').open('wb') as se:
            proc=subprocess.Popen(argv,cwd=work,env=env,stdout=so,stderr=se)
            if stage=='initial':
                limit=time.monotonic()+60
                while not (root/'observed').is_file() and proc.poll() is None and time.monotonic()<limit:time.sleep(.01)
                if not (root/'observed').is_file():
                    if proc.poll() is None:proc.kill();proc.wait()
                    raise RuntimeError(('first macro never observed input',kind,(rec/'stderr').read_text()[-1800:]))
                assert (root/'observed').read_text().strip()=='17'
                swap=real.with_name(real.name+'.replacement');shutil.copyfile(alt,swap) if kind=='external-rlib' else swap.write_bytes(b'29')
                if stamp=='preserved':os.utime(swap,ns=(real.stat().st_atime_ns,before['mtime']))
                os.replace(swap,real);after=stable(real);assert before['size']==after['size'] and before['sha256']!=after['sha256'] and before['inode']!=after['inode'];assert after['mtime']==before['mtime'] if stamp=='preserved' else after['mtime']>before['mtime']
                (root/'release').write_text('1');(root/'armed').unlink()
            rc=proc.wait(timeout=120)
        events=[json.loads(l) for l in (rec/'stdout').read_bytes().splitlines()]
        if rc!=0:
            errors=[v['message']['message'] for v in events if v.get('reason')=='compiler-message' and v['message']['level']=='error']
            assert kind=='external-rlib' and stage=='initial' and rc==101 and events[-1]=={'reason':'build-finished','success':False} and errors==['found crates (`escape_fixture` and `escape_fixture`) with colliding StableCrateId values'],(stage,kind,rc,errors)
            z=dict(value=None,fresh=False,claim_complete=False,exit=rc,diagnostics=errors,trace=digest(rec/'exec'),native=False)
            rows[stage]=z;(rec/'result.json').write_text(json.dumps(z,sort_keys=True,indent=2)+'\n');continue
        assert events[-1]=={'reason':'build-finished','success':True}
        row,=[x for x in events if x.get('reason')=='compiler-artifact' and x['target']['name']=='hold_direct'];exe=Path(row['executable']);program=run([exe]);assert not program.stderr
        (rec/'native').write_bytes(program.stdout); value=int([line[7:] for line in program.stdout.decode().splitlines() if line.startswith('sample=')][0]);assert value in (17,29)
        dep,=[p for d in (target,shared) for p in d.rglob('hold_direct*.d') if p.parent.name=='out' and b'ohm-foreign-span-bytes' in p.read_bytes()];proof,=[p for d in (target,shared) for p in d.rglob('dep-bin-hold_direct') if b'OBS1' in p.read_bytes()];data=dep.read_bytes();encoded=proof.read_bytes();assert encoded[5]==4 and encoded[-41:-37]==b'OBS1';(rec/'rustc.d').write_bytes(data);(rec/'cargo.fingerprint').write_bytes(encoded)
        header=[l for l in data.splitlines() if l.startswith(b'# ohm-observer-inputs-v1 ')];assert len(header)<=1
        full=bytes.fromhex(header[0].split(b' ')[3].decode()) if header else data
        checks=[l.decode() for l in full.splitlines() if l.startswith(b'# checksum:') and l.endswith(str(real).encode())]
        z=dict(value=value,claim_complete=bool(encoded[-33]),fresh=row['fresh'],all_fresh=all(x['fresh'] for x in events if x.get('reason')=='compiler-artifact'),exe=digest(exe),dep=digest(dep),proof=digest(proof),receipt=bool(header),input_checksum=checks,trace=digest(rec/'exec'))
        rows[stage]=z;(rec/'result.json').write_text(json.dumps(z,indent=2,sort_keys=True)+'\n')
    assert (rows['initial']['value']==17 or (kind=='external-rlib' and rows['initial'].get('exit')==101)) and rows['clean']['value']==29 and stable(real)==after
    out=dict(kind=kind,stamp=stamp,first_input=before,changed_input=after,rows=rows);(root/'result.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');return {k:(v['value'],v['fresh'],v['claim_complete']) for k,v in rows.items()}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--sdk',type=Path,required=True);a=p.parse_args();a.root.mkdir();summary={}
    for kind in ('external-rlib','tracked-file'):
        for stamp in ('current','preserved'):
            label=kind+'-'+stamp;summary[label]=run_case(a.root/label,a.sdk,kind,stamp);print(label,summary[label],flush=True)
    (a.root/'complete.json').write_text(json.dumps(summary,indent=2)+'\n')
