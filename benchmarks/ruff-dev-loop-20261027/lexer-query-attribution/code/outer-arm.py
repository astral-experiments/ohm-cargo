from pathlib import Path
import base64,hashlib,json,subprocess
d=Path(__file__).resolve().parent
files={n:(d.parent/n).read_bytes()for n in ('module-parents','module-parents.c')};files['outer.py']=(d/'outer.py').read_bytes()
for arm in 'BC':files['kinds-'+arm+'.json']=json.dumps(json.loads((d.parent/('writer-kinds-'+arm+'.json')).read_bytes())['kinds']).encode()
code="""from pathlib import Path
import json,os,subprocess,base64,sys,hashlib
root=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/pr233-h5-lexer-graph-witness-v2a/typed-queries/immediate-readers');root.mkdir(mode=0o700)
files=json.load(sys.stdin);dig={}
for n,x in files.items():v=base64.b64decode(x);(root/n).write_bytes(v);dig[n]=hashlib.sha256(v).hexdigest()
(root/'module-parents').chmod(0o700);(root/'binding.json').write_text(json.dumps(dig))
with (root/'watch.log').open('x') as lg:p=subprocess.Popen(['nice','-n','19','taskset','-c','30,31',sys.executable,'-B',str(root/'outer.py')],stdin=subprocess.DEVNULL,stdout=lg,stderr=lg,start_new_session=True)
print(p.pid,dig)
"""
print(subprocess.check_output(['dbox','ssh','charlie-ohm-loader-perf-1024','--no-tmux','--','/usr/bin/python3','-B','-c',code],input=json.dumps({k:base64.b64encode(v).decode()for k,v in files.items()}).encode()).decode())
