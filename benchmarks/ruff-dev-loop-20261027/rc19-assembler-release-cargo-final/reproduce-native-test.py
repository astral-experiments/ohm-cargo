"""Execute the literal product-test sources against an unwrapped released toolchain."""
import os,sys,re,json,hashlib,subprocess
from pathlib import Path
root=Path(sys.argv[1]).absolute();sdk=Path(sys.argv[2]).resolve();test_source=Path(sys.argv[3]).resolve();opt=sys.argv[4:]
d=root/'project';d.mkdir(parents=True)
def w(fn,b):p=d/fn;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(b)
text=test_source.read_text().split('fn dependency_edit_reassembles_native_targets_by_default() {',1)[1].split('\n}\n',1)[0]
for name in ('input.rs','tests/integration.rs','src/bin/reader.rs'):
 m=re.search(re.escape('"'+name+'"')+r',\s*r#"(.*?)"#',text,re.S);assert m,name;w(name,m[1])
w('Cargo.toml','[package]\nname="app"\nversion="0.1.0"\nedition="2015"\n');w('src/lib.rs','pub fn value() -> u8 { 1 }');w('payload.bin','A')
bind=root/'rustup/toolchains';bind.mkdir(parents=True);(bind/'ohm').symlink_to(sdk,target_is_directory=True)
proxy=Path(os.environ['HOME'])/'.cargo/bin/cargo'
env=dict(HOME=str(root/'home'),CARGO_HOME=str(root/'cargo-home'),RUSTUP_HOME=str(root/'rustup'),RUSTUP_AUTO_INSTALL='0',PATH=str(proxy.parent)+':/usr/bin:/bin',CARGO_TARGET_DIR=str(root/'target'),CARGO_BUILD_BUILD_DIR=str(root/'shared'),CARGO_INCREMENTAL='0',LANG='C.UTF-8')
rows=[]
for i,expected in enumerate(['1:65','22:66','']):
 if i:w('src/lib.rs','pub fn value() -> u8 { '+('22' if i==1 else '3')+' }')
 if i==1:w('payload.bin','B')
 if i==2:(d/'payload.bin').unlink()
 o=root/str(i);o.mkdir();cmd=['strace','-ff','-qq','-s','16000','-e','trace=execve,open,openat','-o',str(o/'syscall'),str(proxy),'+ohm','-Zohm-defaults',*opt,'test','--test','integration','-j2','--message-format=json']
 q=subprocess.run(cmd,cwd=d,env=dict(env,EXPECTED=expected),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 for f,raw in [('stdout',q.stdout),('stderr',q.stderr)]: (o/f).write_bytes(raw)
 if b'Operation not permitted' in q.stderr and not q.stdout: raise Exception(q.stderr.decode())
 records=[json.loads(l) for l in q.stdout.splitlines() if l.startswith(b'{')];assert any(x['reason']=='build-finished' for x in records),(q.returncode,q.stderr[:500])
 full=[];links=[];opens=[]
 for f in sorted(o.glob('syscall.*')):
  for l in f.read_text(errors='replace').splitlines():
   if l.startswith('execve(') and l.endswith('= 0') and '--crate-name' in l and '/rustc"' in l:
    m=re.search(r'"--crate-name", "([a-z_]+)"',l)
    if m and m[1] in ['reader','integration','app']:(links if '"link-only"' in l or '"-Zlink-only"' in l else full).append(m[1])
   if l.startswith(('open(', 'openat(')) and '/payload.bin"' in l:opens.append('missing' if 'ENOENT' in l else 'present')
 exe=root/'target/debug/reader';probe=subprocess.run([exe],cwd=d,env=env,stdout=subprocess.PIPE) if exe.exists() else None
 rows.append({'phase':i,'cargo':q.returncode,'native':probe.stdout.decode().strip() if probe else None,'full':sorted(full),'link':sorted(links),'payload_opens':opens,'executable':hashlib.sha256(exe.read_bytes()).hexdigest() if exe.exists() else None})
 print(rows[-1],flush=True)
(root/'result.json').write_text(json.dumps(rows,indent=2)+'\n')
