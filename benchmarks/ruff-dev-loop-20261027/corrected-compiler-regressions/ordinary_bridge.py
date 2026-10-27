"""Verify that Cargo sees the library's explicit package-level public-hash opt-out."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser()
for k in ('sysroot','rustup','driver','cargo','out'):p.add_argument('--'+k,required=True,type=Path)
p.add_argument('--cpu',default='0-3');a=p.parse_args()
for k in ('sysroot','rustup','driver','cargo','out'):setattr(a,k,getattr(a,k).absolute())
root=a.out;root.mkdir(exist_ok=False)
sysroot_driver,=(a.sysroot/'lib').glob('librustc_driver*.so')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
def store(path,data):path.write_bytes(gzip.compress(data,mtime=0))
versions={'driver':sha(a.driver),'rustc':sha(a.sysroot/'bin/rustc'),'cargo':sha(a.cargo)}
(root/'toolchains.json').write_text(json.dumps(versions,indent=2)+'\n')
for case in ('macro','private-impl'):
    q=root/case;q.mkdir();ws=q/'workspace';ws.mkdir()
    (ws/'Cargo.toml').write_text('''cargo-features = ["profile-rustflags"]
[workspace]
members = ["review_producer","review_bridge","review_consumer"]
resolver = "3"
[profile.dev]
opt-level = 1
debug = "line-tables-only"
lto = "off"
[profile.dev.package.review_bridge]
rustflags = ["-Zpublic-api-hash=no"]
''')
    for crate,dep in [('review_producer',None),('review_bridge','review_producer'),('review_consumer','review_bridge')]:
        sub=ws/crate;(sub/'src').mkdir(parents=True)
        (sub/'Cargo.toml').write_text(f'[package]\nname="{crate}"\nversion="0.1.0"\nedition="2024"\n'+(f'[dependencies]\n{dep}={{path="../{dep}"}}\n' if dep else ''))
    if case=='macro':
        prod='''#![allow(dead_code,unused_macros)]
macro_rules! noise { () => { struct Noise; } }
macro_rules! make { () => { pub struct Public { pub value: u32 } } }
#[cfg(any())] noise!();
make!();
'''
    else:
        prod='''#![allow(dead_code)]
#[cfg(any())] struct Noise;
pub struct Public { pub value: u32 }
struct Private;
impl Iterator for Private { type Item = u8; fn next(&mut self) -> Option<Self::Item> { None } }
'''
    mod=prod.replace('cfg(any())','cfg(all())').replace('= u8;', '= i8;')
    bridge=ws/'review_bridge/src/lib.rs'
    bridge.write_text('pub use review_producer::*; #[inline] pub fn read(x:review_producer::Public)->u32 {x.value}\n')
    src=ws/'review_producer/src/lib.rs';consumer=ws/'review_consumer/src/main.rs'
    app='fn main(){println!("{}",review_bridge::read(review_bridge::Public{value:7}));}\n'
    src.write_text(prod);consumer.write_text(app)
    wrap=q/'observe-argv';wrap.write_text('''#!/usr/bin/env python3
from pathlib import Path
import os,sys
a=sys.argv[1:]
if '--crate-name' in a:
    n=a[a.index('--crate-name')+1]
    if n.startswith('review_'): (Path(os.environ['ARGV'])/(str(os.getpid())+'-'+n+'.argv')).write_bytes(b'\\0'.join(map(os.fsencode,a)))
os.execv(a[0],a)
''');wrap.chmod(0o755)
    ns=['taskset','-c',a.cpu,'bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
        '--bind',str(q),str(q),'--ro-bind',str(a.cargo),str(a.sysroot/'bin/cargo'),'--ro-bind',str(a.driver),str(sysroot_driver),'--chdir',str(ws),'--']
    def build(phase,store_name):
        rec=q/phase;rec.mkdir();(rec/'calls').mkdir();target=q/(store_name+'-target')
        e=dict(os.environ,RUSTUP_HOME=str(a.rustup),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',
              CARGO_HOME=str(q/'cargo-home'),CARGO_INCREMENTAL='1',CARGO_BUILD_JOBS='4',CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(q/(store_name+'-shared')),
              RUSTC=str(a.sysroot/'bin/rustc'),RUSTC_WRAPPER=str(wrap),ARGV=str(rec/'calls'),GIT_OPTIONAL_LOCKS='0')
        for v in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WORKSPACE_WRAPPER'):e.pop(v,None)
        cmd=[*ns,str(Path.home()/'.cargo/bin/cargo'),'+ohm','build','--offline','-p','review_consumer','--message-format=json'];cp=subprocess.run(cmd,env=e,capture_output=True)
        store(rec/'cargo.stdout.gz',cp.stdout);store(rec/'cargo.stderr.gz',cp.stderr)
        modes={}
        for f in (rec/'calls').glob('*.argv'):
            av=[x.decode() for x in f.read_bytes().split(b'\0')];crate=av[av.index('--crate-name')+1]
            pubs=[x for x in av if 'public-api-hash' in x]
            modes[crate]={'public_flags':pubs,'link_only':any(x in ('link-only','-Zlink-only') for x in av)}
        obj={'exit':cp.returncode,'children':modes}
        artifacts={m['target']['name']:m for m in [json.loads(l)for l in cp.stdout.splitlines() if l.startswith(b'{')] if m['reason']=='compiler-artifact'}
        if cp.returncode:
            obj['failure']=cp.stderr.decode(errors='replace')[-1600:]
        else:
            exe=Path(artifacts['review_consumer']['executable']);run=subprocess.run([str(exe)],capture_output=True)
            obj.update(run_exit=run.returncode,stdout=run.stdout.decode().strip(),elf=sha(exe))
        if (hs:=list(target.rglob('lib-review_producer.public-api-hash'))):obj['producer_hash']=json.loads(hs[0].read_bytes())['value']
        if 'review_bridge' in artifacts:
            obj['bridge_rmeta']=sha(next(Path(f)for f in artifacts['review_bridge']['filenames'] if f.endswith('.rmeta')))
        return obj
    rows={}
    for name,changed,edited in [('prime',False,False),('producer-edit',True,False),('caller-edit',True,True),('producer-restore',False,True),('caller-restore',False,False)]:
        source=mod if changed else prod;main=app.replace('value:7','value:11') if edited else app
        if src.read_text()!=source:src.write_text(source)
        if consumer.read_text()!=main:consumer.write_text(main)
        warm=build(name,'warm');cold=build(name+'-clean',name+'-clean') if name in ('caller-edit','caller-restore') else None
        rows[name]=dict(warm=warm,cold=cold);(q/'observations.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(case,name,warm['exit'],warm.get('producer_hash'),list(warm['children']),warm.get('stdout'),flush=True)
        assert warm['exit']==0,(case,name,warm)
        if cold:
            assert cold['exit']==0 and cold['run_exit']==warm['run_exit']==0 and cold['stdout']==warm['stdout'] and cold['elf']==warm['elf'],(case,name,warm,cold)
    assert rows['prime']['warm']['children']['review_producer']['public_flags'][-1] in ('-Zpublic-api-hash','-Zpublic-api-hash=yes')
    assert rows['prime']['warm']['children']['review_bridge']['public_flags'][-1]=='-Zpublic-api-hash=no'
    for ph in ('producer-edit','producer-restore'):
        assert rows[ph]['warm']['children']['review_bridge']['link_only'] is False,(case,ph,rows[ph])
