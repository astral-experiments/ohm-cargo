"""Test the installed Rust binary-dependencies and BLAKE3 options on an assemble-time read."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
a=Path(sys.argv[1]).absolute();a.mkdir(mode=0o700);sdk=Path(sys.argv[2]).resolve();fixture=Path(sys.argv[3]).resolve()
home=a/'rustup/toolchains';home.mkdir(parents=True);(home/'ohm').symlink_to(sdk,target_is_directory=True)
env=dict(os.environ,RUSTUP_AUTO_INSTALL='0',RUSTUP_HOME=str(a/'rustup'));(a/'upstream.rs').write_bytes((fixture/'engine/src/lib.rs').read_bytes())
(a/'main.rs').write_text('#![forbid(unsafe_code)]\nfn main(){ println!("{}", engine::payload::<u32>()); }\n')
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def do(label,argv):
 o=a/label;o.mkdir(); r=subprocess.run(argv,env=env,cwd=a,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 for n,data in [('stdout',r.stdout),('stderr',r.stderr)]: (o/n).write_bytes(data)
 return r
assert not (a/'untracked.bin').exists()
args=['rustc','+ohm','--edition=2021','-Zbinary-dep-depinfo=yes','-Zchecksum-hash-algorithm=blake3','-Copt-level=0','-Ccodegen-units=4']
u=do('upstream',args+['--crate-name','engine','--crate-type=rlib','--emit=link=libengine.rlib,dep-info=engine.d','upstream.rs']);assert u.returncode==0,u.stderr
up=h(a/'libengine.rlib');rows=[]
for tag,value in [('old',17),('changed',29),('missing',None),('restored',17)]:
 p=a/'untracked.bin'
 if value is None:p.unlink()
 else:p.write_bytes(bytes([value]))
 r=do(tag,args+['--crate-name','consumer','--extern','engine=libengine.rlib','--emit=link='+tag+'/program,dep-info='+tag+'/consumer.d','main.rs'])
 dep=a/tag/'consumer.d';b=dep.read_bytes();assert b'libengine.rlib' in b and b'# checksum:' in b and b'untracked.bin' not in b
 status=None;elf=None
 if value is None:assert r.returncode==1 and b'untracked.bin' in r.stderr
 else:
  assert r.returncode==0,r.stderr;f=a/tag/'program';native=subprocess.run([f],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE); assert native.returncode==0 and native.stdout==str(value).encode()+b'\n';status=native.stdout.decode().strip();elf=h(f)
 assert h(a/'libengine.rlib')==up
 rows.append({'state':tag,'return':r.returncode,'program':status,'depinfo_sha256':h(dep),'contains_external_rlib':True,'contains_checksums':True,'contains_assembler_file':False,'elf':elf,'stderr_sha256':h(a/tag/'stderr')})
j={'compiler':h(sdk/'bin/rustc'),'upstream_rlib_sha256':up,'upstream_compiled_without_payload':True,'rust_args':args,'rows':rows}
(a/'result.json').write_text(json.dumps(j,indent=2,sort_keys=True)+'\n')
print([(s['state'],s['return'],s['program']) for s in rows],flush=True)
