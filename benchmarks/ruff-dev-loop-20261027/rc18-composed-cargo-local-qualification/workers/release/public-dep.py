"""Check exported Make depfiles, including duplicates and a path with a literal space."""
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-rc18-pgo-output-dep-20261028')
X=Path('/dev/shm/ohm-ron-consumed-v1-20261028');SDK=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
arms={'qc':('target-default-guard','5e37d20fa6f79cfcc5a273fb7a95eb19f7239ba750c8a3d1aeaedb90171cdd36'),'rc':('target-rc18-composed','cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8')}
def sha(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
if len(sys.argv)>1:
    arm=sys.argv[1];d=H/arm;w=H/'workspace';s=H/'active';assert sha(SDK/'bin/cargo')==arms[arm][1]
    e={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO'))};e.update(PATH=os.environ['PATH'],RUSTUP_HOME=str(H/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(s/'cargo'),CARGO_TARGET_DIR=str(s/'target'),CARGO_BUILD_BUILD_DIR=str(s/'shared'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='4')
    rows={};dep=s/'target/debug/consumer.d';elf=dep.with_suffix('')
    for phase in ('built','regenerated','unchanged'):
        rec=d/phase;rec.mkdir()
        if phase=='regenerated':dep.unlink()
        with (rec/'cargo.jsonl').open('xb')as o,(rec/'stderr').open('xb')as er:
            p=subprocess.run(['strace','-f','-qq','-s','8192','-e','trace=execve','-o',str(rec/'exec'),'cargo','+ohm','build','--offline','--message-format=json'],cwd=w,env=e,stdout=o,stderr=er,timeout=90)
        assert p.returncode==0,(arm,phase,(rec/'stderr').read_text());raw=dep.read_bytes();(rec/'consumer.d').write_bytes(raw)
        assert (str(w/'provider').encode()+rb'/tracked\ file') in raw and str(w/'provider/build.rs').encode() in raw,raw
        assert raw.count(str(w/'provider').encode()+rb'/tracked\ file')==1 and rb'/./tracked\ file' not in raw,raw
        assert b'/src/../asset' in raw and str(w/'src/main.rs').encode() in raw
        assert subprocess.check_output([elf])==b'29\n'
        events=[json.loads(l) for l in (rec/'cargo.jsonl').read_text().splitlines()];fresh={a['target']['name']:a['fresh'] for a in events if a['reason']=='compiler-artifact'}
        true=[l for l in (rec/'exec').read_text().splitlines() if '"--crate-name",' in l and '"___"' not in l and l.rstrip().endswith('= 0')]
        if phase!='built':assert all(fresh.values()) and not true and sha(elf)==rows['built']['elf'] and rows['built']['raw']==sha(dep),(phase,true,fresh)
        rows[phase]={'raw':sha(dep),'elf':sha(elf),'fresh':fresh,'rustcs':len(true),'cargo':sha(SDK/'bin/cargo')};save(rec/'row.json',rows[phase])
    save(d/'complete.json',rows);sys.exit()
H.mkdir(mode=0o700);(H/'active').mkdir();w=H/'workspace';(w/'src').mkdir(parents=True);(w/'provider/src').mkdir(parents=True);(H/'rustup/toolchains').mkdir(parents=True);(H/'rustup/toolchains/ohm').symlink_to(SDK)
(w/'Cargo.toml').write_text('[package]\nname="consumer"\nversion="0.1.0"\nedition="2021"\n[dependencies]\nproducer={path="provider"}\n[workspace]\n')
(w/'src/main.rs').write_text('fn main(){println!("{}",producer::read());}')
(w/'provider/Cargo.toml').write_text('[package]\nname="producer"\nversion="0.1.0"\nedition="2021"\n')
(w/'provider/src/lib.rs').write_text('pub fn read()->u8{include_bytes!("../asset")[0]}')
(w/'provider/build.rs').write_text('fn main(){println!("cargo::rerun-if-changed=build.rs");println!("cargo::rerun-if-changed=tracked file");println!("cargo::rerun-if-changed=./tracked file");}')
(w/'provider/tracked file').write_bytes(b'x');(w/'provider/asset').write_bytes(bytes([29,255]))
out={}
for name,(folder,expected) in arms.items():
    image=Path('/mnt/devbox-scratch/dev-user/ohm-rc18-pgo-qualification-20261028/cargo') if name=='rc' else X/folder/'debug/cargo';assert sha(image)==expected;d=H/name;d.mkdir();(d/'state').mkdir()
    for z in ('cargo','target','shared'):(d/'state'/z).mkdir()
    o=subprocess.run(['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--tmpfs','/tmp','--bind',str(H),str(H),'--bind',str(d/'state'),str(H/'active'),'--ro-bind',str(image),str(SDK/'bin/cargo'),'--','taskset','-c','4-5',sys.executable,'-B',__file__,name],capture_output=True,timeout=180)
    (d/'worker.stderr').write_bytes(o.stderr);assert o.returncode==0,o.stderr[-1300:];out[name]=json.loads((d/'complete.json').read_text())
assert (H/'qc/built/consumer.d').read_bytes()==(H/'rc/regenerated/consumer.d').read_bytes()
save(H/'complete.json',out);print({arm:r['built']['raw'] for arm,r in out.items()})
