from pathlib import Path
import argparse,hashlib,json,os,signal,subprocess,time
a=argparse.ArgumentParser();a.add_argument('root',type=Path);a.add_argument('--expect',choices=['blocked','fixed'],required=True);o=a.parse_args();root=o.root.resolve();root.mkdir();os.chdir(root)
actual=root/'actual library';decoy=root/'actual\\ library';actual.mkdir();decoy.mkdir();actual=actual/'libd.rlib';decoy=decoy/'libd.rlib';os.mkfifo(decoy)
(root/'d.rs').write_text('pub fn value()->u32{17}\n');(root/'main.rs').write_text('fn main(){println!("{}",d::value());}\n')
def output(args):return subprocess.check_output(args,cwd=root).decode()
output(['rustc','+ohm','--crate-name','d','--crate-type=rlib','d.rs','-o',str(actual)])
args=['rustc','+ohm','--edition=2021','main.rs','--extern','d='+str(actual),'-Zbinary-dep-depinfo','-Zchecksum-hash-algorithm=sha256','--emit=dep-info=result.d,link=app']
with (root/'stdout').open('wb') as out,(root/'stderr').open('wb') as err:
 child=subprocess.Popen(args,stdout=out,stderr=err,start_new_session=True)
 try:rc=child.wait(timeout=6)
 except subprocess.TimeoutExpired:rc=None
 waits={}
 if rc is None:
  for t in Path('/proc',str(child.pid),'task').glob('*'):
   try:waits[t.name]={'wchan':(t/'wchan').read_text().strip(),'syscall':(t/'syscall').read_text().strip()}
   except (OSError,PermissionError):pass
  os.killpg(child.pid,signal.SIGKILL);child.wait()
native=output(['./app']).strip() if rc==0 else None
report=dict(argv=args,unmodified_frontend=output(['rustc','+ohm','-vV']),returncode_before_timeout=rc,timeout_seconds=6,native=native,kernel=waits,fifo=str(decoy),genuine=str(actual),genuine_sha256=hashlib.sha256(actual.read_bytes()).hexdigest(),no_writer_opened=True)
(root/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
assert (rc is None and any('partner' in s['wchan'] for s in waits.values())) if o.expect=='blocked' else (rc==0 and native=='17' and report['genuine_sha256'] in Path('result.d').read_text())
print(o.expect,rc,native,[s['wchan'] for s in waits.values()])
