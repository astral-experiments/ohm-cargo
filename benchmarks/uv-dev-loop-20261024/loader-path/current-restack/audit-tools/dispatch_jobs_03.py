import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import client

R = client.ROOT
os.umask(0o077)
label = sys.argv[1]
job_names = sys.argv[2:]
assert label.replace('-', '').isalnum() and job_names
remote_root = '/home/dev-user/ohm-loader-restack-20261024'
files = {}
jobs = []
for name in job_names:
    p = R / (name + '.json')
    job = json.loads(p.read_bytes())
    assert job['name'] == name
    jobs.append({'name': name, 'bytes': base64.b64encode(p.read_bytes()).decode(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    for row in job['files']:
        local = R / Path(row['path']).name
        data = local.read_bytes()
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        files[row['path']] = {'path': row['path'], 'bytes': base64.b64encode(data).decode(), 'sha256': row['sha256']}
payload = json.dumps({'files': list(files.values()), 'jobs': jobs}, sort_keys=True).encode()
program = r'''import base64,hashlib,json,os,shlex,subprocess,sys
from pathlib import Path
os.umask(0o077)
r=Path('/home/dev-user/ohm-loader-restack-20261024');socket=r/'control/tmux.sock'
data=json.load(sys.stdin);controls=r/'incoming/controls';controls.mkdir(mode=0o700,exist_ok=True)
for row in data['files']:
    p=Path(row['path']);assert p.parent==controls
    b=base64.b64decode(row['bytes'],validate=True);assert hashlib.sha256(b).hexdigest()==row['sha256']
    if p.exists():assert p.read_bytes()==b
    else:
        with p.open('xb') as f:f.write(b)
for row in data['jobs']:
    b=base64.b64decode(row['bytes'],validate=True);assert hashlib.sha256(b).hexdigest()==row['sha256']
    p=controls/(row['name']+'.json')
    with p.open('xb') as f:f.write(b)
if not socket.exists():
    subprocess.run(['/usr/bin/tmux','-S',str(socket),'new-session','-d','-s','keeper','/bin/sleep','infinity'],check=True)
subprocess.run(['/usr/bin/tmux','-S',str(socket),'set-window-option','-g','remain-on-exit','on'],check=True)
for row in data['jobs']:
    name=row['name'];assert name.replace('-','').isalnum()
    prefix=r/'logs'/(name+'.owner')
    for suffix in ('.stdout','.stderr','.stdin'):assert not Path(str(prefix)+suffix).exists()
    Path(str(prefix)+'.stdin').write_bytes(b'')
    for suffix in ('.started.json','.terminal.json'):assert not (r/'records'/(name+suffix)).exists()
    started=subprocess.Popen(['/usr/bin/tmux','-S',str(socket),'wait-for',name+'-started'])
    complete=subprocess.Popen(['/usr/bin/tmux','-S',str(socket),'wait-for',name+'-complete'])
    argv=['/usr/bin/python3','-I','-B',str(controls/'exec_owner_02.py'),str(controls/(name+'.json'))]
    subprocess.run(['/usr/bin/tmux','-S',str(socket),'new-window','-d','-t','keeper','-n',name,*argv],check=True)
    print(json.dumps({'dispatch':name,'argv':argv,'job_sha256':row['sha256']}),flush=True)
    try:assert started.wait(timeout=30)==0
    except BaseException:
        started.terminate();complete.terminate();raise
    print(json.dumps({'owner_started':json.loads((r/'records'/(name+'.started.json')).read_bytes())}),flush=True)
    assert complete.wait(timeout=14400)==0
    terminal=json.loads((r/'records'/(name+'.terminal.json')).read_bytes())
    print(json.dumps({'owner_terminal':terminal}),flush=True)
    assert terminal['state']=='complete' and terminal['failure'] is None
    if name=='smoke-03':assert json.loads((r/'records/inert-owner-smoke.json').read_bytes())['inert_smoke'] is True
'''
prefix = R / label
Path(str(prefix) + '.remote.py').write_text(program)
Path(str(prefix) + '.stdin.json').write_bytes(payload)
record = {'host': client.HOST, 'jobs': job_names, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'program_sha256': hashlib.sha256(program.encode()).hexdigest(), 'payload_sha256': hashlib.sha256(payload).hexdigest()}
with Path(str(prefix) + '.stdin.json').open('rb') as fi, Path(str(prefix) + '.stdout').open('xb') as fo, Path(str(prefix) + '.stderr').open('xb') as fe:
    p = subprocess.Popen(client.ssh('python3 -I -B -c ' + shlex.quote(program)), env=client.environment(), stdin=fi, stdout=fo, stderr=fe, start_new_session=True)
    record['pid'] = p.pid
    Path(str(prefix) + '.started.json').write_text(json.dumps(record, indent=2) + '\n')
    code = p.wait(timeout=15000)
record.update(returncode=code, ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
Path(str(prefix) + '.receipt.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
raise SystemExit(code)
