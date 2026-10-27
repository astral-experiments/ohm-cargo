from pathlib import Path
import json,sys,subprocess,hashlib,base64
d=Path(__file__).resolve().parent
files={i:(d.parent/i).read_bytes()for i in ('query-graph','query-graph.c','scan.py','kinds.json')};files['restore.py']=(d/'restore.py').read_bytes()
s="""from pathlib import Path
import base64,hashlib,json,subprocess,sys,os
out=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/pr233-h5-lexer-graph-witness-v2a');p=out/'typed-queries';p.mkdir(mode=0o700)
v=json.loads(sys.stdin.buffer.read());m={}
for n,b in v.items():r=base64.b64decode(b);m[n]=hashlib.sha256(r).hexdigest();(p/n).write_bytes(r)
(p/'query-graph').chmod(0o700);(p/'binding.json').write_text(json.dumps(m,sort_keys=True)+'\n')
e=os.environ.copy();e['PYTHONPATH']=str(out)
with (p/'watch.log').open('x')as log:q=subprocess.Popen(['nice','-n','19','taskset','-c','30,31',sys.executable,'-B',str(p/'restore.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=e,start_new_session=True)
print(q.pid,json.dumps(m))
"""
s=s.replace("+'\n')","+'\\n')")
print(subprocess.check_output(['dbox','ssh','charlie-ohm-loader-perf-1024','--no-tmux','--','/usr/bin/python3','-B','-c',s],input=json.dumps({k:base64.b64encode(v).decode()for k,v in files.items()}).encode()).decode())
