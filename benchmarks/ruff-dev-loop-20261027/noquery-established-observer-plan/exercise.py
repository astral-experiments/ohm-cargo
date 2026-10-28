"""Reproduce first and trained Cargo observer behavior across three real input acquisition paths."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

HERE=Path(__file__).resolve().parent
KINDS=('tracked-file','include-bytes','include-str')


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def store(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')

def state(p):
    st=p.stat();return dict(inode=st.st_ino,size=st.st_size,mtime=st.st_mtime_ns,sha256=sha(p))


def case(root,sdk,kind,trained,stamp):
    root.mkdir();work=root/'src';shutil.copytree(HERE/'fixture',work)
    rustup=root/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(sdk)
    env=dict(HOME=str(root),PATH=os.environ['PATH'],RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(root/'cargo'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='4',OHM_SYNC_DIR=str(root),OHM_SYNC_CONSTANT='fixed',LC_ALL='C.UTF-8',LANG='C.UTF-8')
    def run(cmd):return subprocess.run(cmd,env=env,cwd=work,check=True,capture_output=True,timeout=120)
    assert Path(run(['rustc','+ohm','--print','sysroot']).stdout.decode().strip()).samefile(sdk)
    data=root/'private-input.txt';payload=lambda n:bytes((255,n)) if kind=='include-bytes' else str(n).encode();data.write_bytes(payload(17));initial=state(data)
    src=work/'hold_direct/src/main.rs';raw=src.read_text();assert raw.count('fn main(){')==1;lit='r#"'+str(data)+'"#';pre='use hold_probe::wait_value;\n';gate='';value='wait_value!(file)'
    if kind=='include-bytes':pre+='const INPUT: &[u8] = include_bytes!('+lit+');\n';gate='const GATE: u32=wait_value!(17);\n';value='INPUT[1]'
    if kind=='include-str':pre+='const INPUT: &str = include_str!('+lit+');\n';gate='const GATE: u32=wait_value!(17);\n';value='INPUT'
    call=pre+gate+raw.replace('fn main(){','fn main(){'+('assert_eq!(GATE,17);' if gate else '')+'println!("sample={}",'+value+');');src.write_text(call);entries={}
    phases=(['train1','train2','train3'] if trained else [])+['change','repeat','again','clean']
    for phase in phases:
        if phase=='change':
            if trained:
                src.write_text(call.replace('fn main(){','fn main(){println!("revision=2");'))
            (root/'armed').write_text('1')
        base=root/('empty' if phase=='clean' else 'warm');target=base/'target';shared=base/'shared';env.update(CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared));dot=root/phase;dot.mkdir()
        cmd=['strace','-f','-qq','-s','65535','-e','trace=execve','-o',str(dot/'exec'),'cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json']
        with (dot/'cargo.jsonl').open('wb') as so,(dot/'cargo.stderr').open('wb') as se:
            p=subprocess.Popen(cmd,env=env,cwd=work,stdout=so,stderr=se,start_new_session=True)
            try:
                if phase=='change':
                    limit=time.monotonic()+65
                    while not (root/'observed').is_file() and p.poll() is None and time.monotonic()<limit:time.sleep(.01)
                    assert (root/'observed').is_file(),('no barrier',kind,trained,stamp,(dot/'cargo.stderr').read_text()[-800:]);assert (root/'observed').read_text().strip()=='17';temp=root/'new-input';temp.write_bytes(payload(29));
                    if stamp=='preserved':os.utime(temp,ns=(data.stat().st_atime_ns,initial['mtime']))
                    os.replace(temp,data);after=state(data);assert after['inode']!=initial['inode'] and after['size']==initial['size'];assert (after['mtime']==initial['mtime']) if stamp=='preserved' else (after['mtime']>initial['mtime']);(root/'release').write_text('1');(root/'armed').unlink()
                rc=p.wait(timeout=120)
            except BaseException:
                if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait()
                raise
        records=[json.loads(l) for l in (dot/'cargo.jsonl').read_bytes().splitlines()];assert rc==0 and records[-1]=={'reason':'build-finished','success':True},(rc,[v['message']['message'] for v in records if v.get('reason')=='compiler-message']);arm,=[r for r in records if r.get('reason')=='compiler-artifact' and r['target']['name']=='hold_direct'];binary=Path(arm['executable']);result=run([binary]);assert not result.stderr;(dot/'program').write_bytes(result.stdout);value,=[int(l[7:]) for l in result.stdout.decode().splitlines() if l.startswith('sample=')];assert value in (17,29)
        ds=[f for d in (target,shared) for f in d.rglob('hold_direct*.d') if f.parent.name=='out' and (b'ohm-foreign-span-bytes' in f.read_bytes() or b'ohm-untrackable-foreign-span' in f.read_bytes())];assert len(ds)==1,ds;dep=ds[0].read_bytes();(dot/'rustc.d').write_bytes(dep)
        fs=[f for d in (target,shared) for f in d.rglob('dep-bin-hold_direct') if f.is_file()];assert len(fs)==1,fs;enc=fs[0].read_bytes();(dot/'fingerprint').write_bytes(enc);obs=enc[-41:-37]==b'OBS1';full=bool(enc[-33]) if obs else None
        hd=[l for l in dep.splitlines() if l.startswith(b'# ohm-observer-inputs-v1 ')];assert len(hd)<=1;ext=bytes.fromhex(hd[0].split(b' ')[3].decode()) if hd else dep;witness=[l.decode() for l in ext.splitlines() if l.startswith(b'# checksum:') and l.endswith(str(data).encode())];entry=dict(value=value,fresh=arm['fresh'],all_fresh=all(r['fresh'] for r in records if r.get('reason')=='compiler-artifact'),initially_complete=full,untrackable=b'ohm-untrackable-foreign-span' in dep,optional=bool(hd),input_checksums=witness,exe=sha(binary),native=sha(dot/'program'),fingerprint=sha(fs[0]),dep=sha(ds[0]),trace=sha(dot/'exec'),caller_sha=sha(src));entries[phase]=entry;store(dot/'row.json',entry)
    assert entries['clean']['value']==29 and state(data)==after and all(entries[x]['value']==17 for x in phases if x.startswith('train'))
    store(root/'report.json',dict(kind=kind,trained=trained,stamp=stamp,before=initial,after=after,rows=entries)); return {k:[v['value'],v['fresh'],v['initially_complete'],v['untrackable']] for k,v in entries.items()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--out',type=Path,required=True);o=p.parse_args();o.out.mkdir();out={}
    for trained in (True,False):
        for kind in KINDS:
            for stamp in ('current','preserved'):
                label=('trained' if trained else 'first')+'-'+kind+'-'+stamp;out[label]=case(o.out/label,o.sdk,kind,trained,stamp);store(o.out/'progress.json',dict(complete=list(out)));print(label,out[label],flush=True)
    store(o.out/'complete.json',out)
