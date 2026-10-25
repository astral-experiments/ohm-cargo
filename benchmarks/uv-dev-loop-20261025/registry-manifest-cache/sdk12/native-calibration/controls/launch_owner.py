"""One persistent owner; exclusive job/start paths prevent a workload retry."""
from pathlib import Path
import argparse
import json
import os
import shlex
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common as C


def main():
    p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True)
    p.add_argument('--job-sha256',required=True);a=p.parse_args()
    os.umask(0o077);os.sched_setaffinity(0,range(9,16))
    assert a.job.parent==C.NATIVE/'incoming/controls'
    job=C.read_ref({'path':str(a.job),'sha256':a.job_sha256});name=job['name']
    assert name==a.job.stem and name.isascii() and name.replace('-','').isalnum()
    for row in job['files']:assert C.sha(row['path'])==row['sha256']
    prefix=C.NATIVE/'records'/name
    assert not Path(str(prefix)+'.started.json').exists() and not Path(str(prefix)+'.terminal.json').exists()
    for directory in ('control','logs','records'):(C.NATIVE/directory).mkdir(exist_ok=True)
    stdin=C.NATIVE/'logs'/(name+'.owner.stdin')
    with stdin.open('xb'):pass
    socket=C.NATIVE/'control/tmux.sock'
    command=['/usr/bin/tmux','-f','/dev/null','-S',str(socket),'new-session','-d','-s',name,
             'exec '+shlex.join(['/usr/bin/python3','-I','-B',str(C.NATIVE/'incoming/controls/exec_owner.py'),str(a.job)]),
             ';','set-option','-s','exit-empty','off']
    C.save(Path(str(prefix)+'.launch-intent.json'),{'job_sha256':a.job_sha256,'argv':command,'utc':C.utc()})
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    C.save(Path(str(prefix)+'.launch-result.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    assert result.returncode==0 and not result.stdout and not result.stderr
    if not Path(str(prefix)+'.started.json').exists():
        subprocess.run(['/usr/bin/tmux','-S',str(socket),'wait-for',name+'-started'],check=True,timeout=60)
    started=json.loads(Path(str(prefix)+'.started.json').read_bytes())
    assert started['job_sha256']==a.job_sha256
    print(json.dumps({'state':'owner-acknowledged','name':name,'owner_pid':started['owner_pid'],
                      'started_at':started['started_at'],'start_sha256':C.sha(Path(str(prefix)+'.started.json'))}),flush=True)


if __name__=='__main__':main()
