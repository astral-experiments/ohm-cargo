"""Exercise the exact OS argument FF on both published toolchains with/without RUST_BACKTRACE."""
from pathlib import Path
import hashlib,json,os,resource,subprocess
out=Path('/mnt/devbox-scratch/dev-user/ohm-release-unicode-panic-scout-20261028');out.mkdir();resource.setrlimit(resource.RLIMIT_CORE,(0,0))
official=Path('/dev/shm/ohm-published-member-h2-20261028/installed17');older=Path('/mnt/devbox-scratch/dev-user/ohm-derive-cache-ci-toolchain-20261028/sdk')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,o):p.write_text(json.dumps(o,sort_keys=True,indent=2)+'\n')
rows=[]
for arm,sdk,release in [('released-17',official,'ohm-1.99.0-17'),('ci-9',older,'ohm-1.98.0-9')]:
 d=out/arm;d.mkdir();ru=d/'rustup';(ru/'toolchains').mkdir(parents=True);(ru/'toolchains/ohm').symlink_to(sdk)
 env={k:v for k,v in os.environ.items() if k not in ('RUST_BACKTRACE','RUST_LIB_BACKTRACE','RUSTC_LOG','RUSTFLAGS','RUSTUP_TOOLCHAIN','__RUSTC_DEFAULT_LOCAL_LIBDIR')};env.update(RUSTUP_HOME=str(ru),RUSTUP_AUTO_INSTALL='0',LANG='C.UTF-8')
 for tool in ['rustc','rustdoc']:
  exe=sdk/'bin'/tool;commit=subprocess.check_output([os.fsencode(exe),b'-Vv'],env=env).decode();assert release in commit,d
  for invocation in ['direct','rustup']:
   for bt in ['unset','zero']:
    case=d/(tool+'-'+invocation+'-'+bt);case.mkdir();e=env.copy()
    if bt=='zero':e['RUST_BACKTRACE']='0'
    av=[os.fsencode(exe),b'\xff'] if invocation=='direct' else [os.fsencode(Path('/home/dev-user/.cargo/bin')/tool),b'+ohm',b'\xff']
    q=subprocess.run(av,env=e,cwd=case,timeout=20,stdout=subprocess.PIPE,stderr=subprocess.PIPE);(case/'stderr').write_bytes(q.stderr);(case/'stdout').write_bytes(q.stdout)
    row=dict(release=release,tool=tool,kind=invocation,backtrace=bt,argv_hex=[x.hex() for x in av],binary_sha256=sha(exe),driver_sha256=sha(next((sdk/'lib').glob('librustc_driver-*.so'))),version=commit.splitlines()[0],exit=q.returncode,stderr=q.stderr.decode(errors='backslashreplace'),stdout=q.stdout.decode(errors='backslashreplace'),stderr_sha256=sha(case/'stderr'),panic=b'panicked at' in q.stderr,diagnostic=b'not valid Unicode' in q.stderr or b'not valid unicode' in q.stderr.lower());save(case/'result.json',row);rows.append(row)
    print(row['release'],tool,invocation,bt,row['exit'],row['panic'],row['diagnostic'],repr(q.stderr[:180]),flush=True)
 save(d/'complete.json',[v for v in rows if v['release']==release])
save(out/'complete.json',rows)
