"""One passive completion notification; no sample or elapsed file is opened."""
from pathlib import Path
import json
import os
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common as C
name=sys.argv[1]
assert name.isascii() and name.replace('-','').isalnum()
os.sched_setaffinity(0,range(9,16))
terminal=C.NATIVE/'records'/(name+'.terminal.json')
if not terminal.exists():
    subprocess.run(['/usr/bin/tmux','-S',str(C.NATIVE/'control/tmux.sock'),'wait-for',name+'-complete'],check=True)
row=json.loads(terminal.read_bytes())
print(json.dumps({'state':row['state'],'owner_pid':row['owner_pid'],'failure':row['failure'],
                  'ended_at':row['ended_at'],'terminal_sha256':C.sha(terminal)}),flush=True)
