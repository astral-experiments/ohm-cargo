"""Run compiler depinfo against a real ordinary file, symlink, missing name and FIFO (no writer)."""
from pathlib import Path
import argparse,json,os,signal,subprocess,shutil,hashlib,time
a=argparse.ArgumentParser();a.add_argument('root',type=Path);a.add_argument('--sdk',type=Path,required=True);a.add_argument('--old',action='store_true');o=a.parse_args();p=o.root.resolve();p.mkdir();sdk=o.sdk.resolve();ru=p/'rustup';(ru/'toolchains').mkdir(parents=True);(ru/'toolchains/ohm').symlink_to(sdk)
env=dict(os.environ,PATH='/home/dev-user/.cargo/bin:'+os.environ['PATH'],RUSTUP_HOME=str(ru),RUSTC_BOOTSTRAP='1');env.pop('RUSTUP_TOOLCHAIN',None)
(p/'mark.rs').write_text('#![feature(proc_macro_tracked_path)]\nextern crate proc_macro;\n#[proc_macro] pub fn mark(_:proc_macro::TokenStream)->proc_macro::TokenStream { proc_macro::tracked::path(std::env::var("TRACK_NAME").unwrap()); proc_macro::TokenStream::new() }');(p/'app.rs').write_text('extern crate mark; mark::mark!(); pub fn retained()->u8{17}')
def run(args,**kw):return subprocess.run(['rustc','+ohm',*args],cwd=p,env=env,timeout=40,check=True,capture_output=True,**kw)
run(['mark.rs','--crate-name','mark','--crate-type','proc-macro','-o',str(p/'libmark.so')])
record={}
for n in ('regular','linked','missing','fifo'):
 path=p/n
 if n=='regular':path.write_bytes(b'abc\xff\x02')
 elif n=='linked':path.symlink_to('regular')
 elif n=='fifo':os.mkfifo(path)
 env['TRACK_NAME']=str(path);args=['rustc','+ohm','app.rs','--edition=2024','--crate-type=lib','--extern','mark='+str(p/'libmark.so'),'-Zchecksum-hash-algorithm=sha256','--emit','metadata,dep-info='+n+'.d']
 o1=p/(n+'.stdout');e1=p/(n+'.stderr');trace=p/(n+'.syscalls')
 with o1.open('wb') as out,e1.open('wb') as err:
  proc=subprocess.Popen(['strace','-f','-qq','-s','256','-e','trace=openat,openat2,newfstatat','-o',str(trace),*args],env=env,cwd=p,start_new_session=True,stdout=out,stderr=err)
  try: rc=proc.wait(timeout=7)
  except subprocess.TimeoutExpired:
   rc=None;os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 dep=p/(n+'.d');rows=dep.read_text().splitlines() if dep.is_file() else []
 checks=[s for s in rows if s.startswith('# checksum:') and s.endswith(' '+str(path))]
 flags=[l for l in trace.read_text().splitlines() if ('"'+str(path)+'",') in l and 'openat' in l]
 record[n]={'returncode':rc,'argv':args,'checksums':checks,'opens':flags,'exists_in_depinfo':any(str(path) in s for s in rows),'writer':False}
 assert (n=='fifo' and o.old and rc is None) or rc==0,(n,rc,e1.read_text()[-450:])
 if n in ['regular','linked']:assert len(checks)==1 and hashlib.sha256(b'abc\xff\x02').hexdigest() in checks[0]
 else: assert not checks
 if not o.old:assert any('O_NONBLOCK' in s and 'O_NOCTTY' in s for s in flags),(n,flags)
 if rc==0:assert record[n]['exists_in_depinfo']
(p/'result.json').write_text(json.dumps(record,indent=2)+'\n');print({n:r['returncode'] for n,r in record.items()})
