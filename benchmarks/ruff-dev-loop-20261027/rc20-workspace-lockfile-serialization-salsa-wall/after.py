"""Reopen every empty-source/control/treatment product after completion, read-only."""
from pathlib import Path
import hashlib,json,os,shutil,stat,subprocess,sys
p=Path(__file__).resolve().parent
def read(q):return json.loads(q.read_bytes())
def sha(f):
 with f.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
def put(dst,obj):
 with dst.open('x')as f:json.dump(obj,f,sort_keys=True,indent=1);f.write('\n')
b=read(p/'binding.json');view=Path(b['view']);phys=Path(b['physical']);s=read(p/'seed.json');plan=read(p/'protocol.json')
if len(sys.argv)>1:
 a=sys.argv[1];assert a in ('A','B','C') and os.geteuid()==1000 and Path('/').stat().st_uid==0
 assert int(Path('/proc/self/status').read_text().split('CapEff:\t')[1].splitlines()[0],16)==0 and all(os.statvfs(view/k).f_flag&os.ST_RDONLY for k in ('','products','shared'))
 d=p/'final-products'/a;d.mkdir();fmap={}
 images=plan['toolchain']
 for token,f,digest in [('cargo',view/'sdk/bin/cargo',images['candidate' if a=='B'else'baseline']),('rustc',view/'sdk/bin/rustc',images['rustc']),('wild',view/'sdk/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd',images['wild']),('manifest',view/'source/Cargo.toml',plan['historical']['original']),('lock',view/'source/Cargo.lock',images['lockfile']),('caller',view/'salsa-wall-consumer',s['caller']),*[(Path(k).suffix[1:],view/k,v) for k,v in s['files'].items()]]:
  st=f.stat();assert stat.S_ISREG(st.st_mode) and sha(f)==digest;fmap[token]={'sha256':digest,'bytes':st.st_size,'mode':st.st_mode&0o7777}
  if token in ('rlib','rmeta','caller'):
   with f.open('rb')as orig,(d/token).open('xb')as target:shutil.copyfileobj(orig,target)
   assert sha(d/token)==digest
 value=subprocess.run([view/'salsa-wall-consumer'],capture_output=True,timeout=10);assert value.returncode==0 and value.stdout==b'17 29 12\n'and not value.stderr
 (d/'stdout').write_bytes(value.stdout);(d/'stderr').write_bytes(value.stderr);put(d/'checked.json',dict(arm=a,files=fmap,read_only=True,euid=os.geteuid(),verdict=value.stdout.decode().strip(),exit=value.returncode,stdout=sha(d/'stdout'),stderr=sha(d/'stderr')))
else:
 assert (p/'score.exit').read_bytes()==b'0\n'and (p/'score.stderr').read_bytes()==b''and read(p/'terminal.json')['record_count']==64 and not (p/'final-products').exists()
 assert shutil.disk_usage(p).free>24*2**30+25*2**20
 (p/'final-products').mkdir(mode=0o700)
 en=read(Path(b['prior_enrollment']))['env']
 sh='''set -eu
mount -t overlay overlay -o "ro,exec,nosuid,nodev,lowerdir=$1" "$2"
for store in products shared; do mount --bind "$3/$store" "$2/$store"; mount -o remount,bind,ro,exec,nosuid,nodev "$2/$store"; done
exec setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs --inh-caps=-all --ambient-caps=-all --bounding-set=-all -- env HOME="$6" USER="$7" LOGNAME="$8" taskset -c 0-3 /usr/bin/python3 -IB "$4" "$5"'''
 for a in 'CAB':
  layers=[phys/'C/upper',Path(b['old_common']),Path(b['lower'])]
  if a!='C':layers.insert(0,phys/a/'upper')
  subprocess.run(['sudo','-n','unshare','--mount','--propagation','private','--','/bin/sh','-ec',sh,'readonly',':'.join(map(str,layers)),str(view),str(phys/a),str(Path(__file__).resolve()),a,*[en[k]for k in ('HOME','USER','LOGNAME')]],check=True)
 put(p/'final-products/closed.json',dict(terminal=sha(p/'terminal.json'),arms={a:sha(p/'final-products'/a/'checked.json')for a in 'CAB'},oracles=['rlib','rmeta','caller','stock compiler','stock linker','unchanged root manifest','lockfile']))
