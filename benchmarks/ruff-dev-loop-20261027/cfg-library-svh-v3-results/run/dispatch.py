from pathlib import Path
import base64,gzip,hashlib,json,subprocess,sys
D=Path(__file__).resolve().parent;P=D.parent/'cfg-library-svh-v3-plan';m=sys.argv[1];files={}
if m=='start':
 binding=json.loads((D/'received.json').read_bytes());assert binding['sha256']=='36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05';(D/'release-binding.json').write_text(json.dumps(binding,indent=1,sort_keys=True)+'\n');fs=[D/'historical.py',D/'release-binding.json',*sorted(P.glob('*'))];files={p.name:base64.b64encode(p.read_bytes()).decode() for p in fs};assert hashlib.sha256((P/'SHA256SUMS').read_bytes()).hexdigest()=='ded79410fa8fe9518e23fa17715005223b5daa923caf60f057a76bddb0c5619b'
elif m=='export':files={'bundle.py':base64.b64encode((D/'bundle.py').read_bytes()).decode()}
remote="""from pathlib import Path
import base64,hashlib,json,os,shutil,sys,subprocess
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';H=X/'cfg-library-svh-v3-impl-v1';V=X/'cfg-library-svh-v3-replay-v1'
if not H.exists():H.mkdir(mode=0o700)
for name,vs in files.items():
 p=H/name;b=base64.b64decode(vs)
 if not p.exists():p.write_bytes(b)
 assert p.read_bytes()==b
"""
if m=='start':
 remote+="""assert not V.exists();assert shutil.disk_usage(X).free>=32*2**30;subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=H,check=True);driver=X/'cfg-library-svh-v3-release/candidate-driver.so'
with driver.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==json.loads((H/'release-binding.json').read_bytes())['sha256']
assert hashlib.sha256((H/'historical.py').read_bytes()).hexdigest()==workhash
p=subprocess.Popen(['nice','-n','12','taskset','-c','24-29','/usr/bin/python3','-B',str(H/'historical.py')],start_new_session=True,stdin=subprocess.DEVNULL,stdout=(H/'run.log').open('xb'),stderr=subprocess.STDOUT);print('pid',p.pid,'sha',workhash)
"""
elif m=='status':
 remote+="""print('last',(H/'run.log').read_text()[-1700:] if (H/'run.log').is_file() else None);print('failure',(V/'failure.txt').read_text()[-1400:] if (V/'failure.txt').is_file() else None,'done',(V/'complete.json').is_file(),'disk',shutil.disk_usage(X).free)
"""
elif m=='export':
 remote+="""assert (V/'complete.json').is_file() or (V/'failure.txt').is_file();subprocess.run(['nice','-n','19','taskset','-c','30','python3','-B',str(H/'bundle.py')],check=True)
"""
else:raise ValueError(m)
ss='import gzip,json,sys\nfiles=json.loads(gzip.decompress(sys.stdin.buffer.read()))\nworkhash='+repr(hashlib.sha256((D/'historical.py').read_bytes()).hexdigest())+'\n'+remote
q=subprocess.run(['dbox','ssh','charlie-ohm-relink-b-1024','--no-tmux','--','nice','-n','19','taskset','-c','30','python3','-B','-c',ss],input=gzip.compress(json.dumps(files).encode()),capture_output=True,timeout=1200)
if m=='export' and q.returncode==0:
 b=base64.b64decode(q.stdout);p=D/'selected.tar.gz';p.write_bytes(b);print(p,len(b),hashlib.sha256(b).hexdigest())
else:sys.stdout.buffer.write(q.stdout)
sys.stderr.buffer.write(q.stderr);sys.exit(q.returncode)
