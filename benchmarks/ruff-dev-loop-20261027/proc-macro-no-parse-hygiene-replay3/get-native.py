"""Commit to every ordinary bridge and native executable left by the release-matched candidate test."""
from pathlib import Path
import json
import subprocess

here=Path(__file__).resolve().parent
code='''
from pathlib import Path
import hashlib,json,os,socket
assert socket.gethostname()=='charlie-ohm-trait-perf-1024'
os.sched_setaffinity(0,{28,29});os.nice(12)
root=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/macro-cargo-hygiene-v3/replay3-hygiene');assert (root/'exit').read_text()=='0'
e=root/'run/evidence';files={}
for p in sorted(e.rglob('*')):
    if p.name not in ('app','libbridge.rlib') or not p.is_file():continue
    with p.open('rb') as f:
        magic=f.read(8);f.seek(0);check=hashlib.file_digest(f,'sha256').hexdigest()
    assert (magic.startswith(b'\\x7fELF') if p.name=='app' else magic==b'!<arch>\\n')
    files[str(p.relative_to(e))]={'size':p.stat().st_size,'sha256':check,'kind':'elf' if p.name=='app' else 'archive'}
print(json.dumps(files,sort_keys=True))
'''
data=subprocess.check_output(['dbox','ssh','charlie-ohm-trait-perf-1024','--no-tmux','--','/usr/bin/python3','-B','-c',code])
files=json.loads(data)
assert sum(v['kind']=='elf' for v in files.values())==16 and sum(v['kind']=='archive' for v in files.values())==8
(here/'native-digests.json').write_text(json.dumps(files,indent=2,sort_keys=True)+'\n')
print(len(files),'actual native products')
