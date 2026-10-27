from pathlib import Path
import json,sys,subprocess,hashlib,base64
d=Path(__file__).resolve().parent;i=d.parent.parent/'pr233-heldout-h5/worker-v2'
dig=lambda b:hashlib.sha256(b).hexdigest()
files={name:(d/name).read_bytes() for name in ('ids.py','capture.py')};sh=[dig(files['capture.py']),dig(files['ids.py']),dig((i/'binding.json').read_bytes()),dig((i/'SHA256SUMS').read_bytes())]
s="""from pathlib import Path
import base64,hashlib,json,subprocess,sys,os
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/pr233-h5-lexer-graph-witness-v2a');p.mkdir(mode=0o700)
fs=json.loads(sys.stdin.buffer.read());assert set(fs)=={'ids.py','capture.py'}
for n,b in fs.items():(p/n).write_bytes(base64.b64decode(b))
assert (p/'capture.py').stat().st_size>2000
with (p/'watch.log').open('x')as log:q=subprocess.Popen(['nice','-n','19','taskset','-c','30,31',sys.executable,'-B',str(p/'capture.py'),*sys.argv[1:]],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(q.pid,p)
"""
print(subprocess.check_output(['dbox','ssh','charlie-ohm-loader-perf-1024','--no-tmux','--','/usr/bin/python3','-B','-c',s,*sh],input=json.dumps({k:base64.b64encode(v).decode()for k,v in files.items()}).encode()).decode())
