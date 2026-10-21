#!/usr/bin/env python3
"""Stage and seal reviewed inputs, or separately launch one approved fixed phase."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'
HOST = 'charlie-oss-2'
SSH = '/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument('--stage', action='store_true')
mode.add_argument('--launch-phase', choices=('ir', 'native'))
parser.add_argument('--sealed-inputs-sha256')
args = parser.parse_args()
binding = json.loads((HERE / 'delivery/binding.json').read_text())
assert sha(HERE / 'delivery/delivery.json') == binding['delivery_sha256']
source = json.loads((HERE / 'source-freeze.json').read_text())
for filename, digest in source['files'].items():
    assert sha(HERE / filename) == digest
review = json.loads((HERE / 'source-review.json').read_text())
assert review['status'] == 'passed' and review['source_freeze_sha256'] == sha(HERE / 'source-freeze.json')
label = 'stage' if args.stage else 'launch-' + args.launch_phase
record = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'operation': label, 'host': HOST, 'root': ROOT, 'delivery_sha256': binding['delivery_sha256'],
          'sealed_inputs_sha256': args.sealed_inputs_sha256}
record_path = HERE / (label + '.json')
assert not record_path.exists()
record_path.write_text(json.dumps(record, indent=2) + '\n')
if args.stage:
    assert sha(HERE / 'delivery/payload.tar') == binding['archive_sha256']
    remote = r'''
import datetime,hashlib,json,os,pathlib,socket,sys,tarfile
root=pathlib.Path(ROOT)
assert socket.gethostname()=='charlie-oss-2' and os.getuid()==1000
assert pathlib.Path('/').stat().st_uid==0 and root.resolve()==root and not os.path.lexists(root)
production=pathlib.Path('/tmp/ohm-hillclimb-20261021-inheritance-production')
status=json.loads((production/'status-host2-inheritance-stack180.json').read_text())
assert status['state']=='complete' and set(status['completed_variants'])=={'inheritance-stack180-baseline','inheritance-stack180-shared'}
exec(compile(OCCUPANCY,'<frozen-occupancy>','exec'))
occupancy=require_quiet()
root.mkdir(mode=0o700)
seen=set()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  name=pathlib.PurePosixPath(member.name)
  assert member.isfile() and not name.is_absolute() and '..' not in name.parts and member.name not in seen
  seen.add(member.name)
  archive.extract(member,path=root,filter='data')
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
assert sha(root/'delivery.json')==EXPECTED_DELIVERY
delivery=json.loads((root/'delivery.json').read_text())
assert delivery['root']==str(root) and delivery['host']==socket.gethostname()
assert seen==set(delivery['files'])|{'delivery.json'}
for name,digest in delivery['files'].items():
 path=root/name;assert path.resolve()==path and sha(path)==digest,name
owner={'root':str(root),'host':socket.gethostname(),'uid':os.getuid(),'delivery_sha256':EXPECTED_DELIVERY,
       'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(root/'ownership.json').write_text(json.dumps(owner,indent=2)+'\n')
(root/'delivery-occupancy.json').write_text(json.dumps(occupancy,indent=2)+'\n')
# Keep one controller PID: the preflight should not mistake its own transfer
# parent for a competing CPU-intensive process.
os.execv('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(root/'controller/prepare_host.py')])
'''.replace('EXPECTED_DELIVERY', repr(binding['delivery_sha256'])).replace('OCCUPANCY', repr((HERE / 'occupancy.py').read_text())).replace('ROOT', repr(ROOT))
    command = [SSH, HOST, '--', '/usr/bin/env', '-u', 'PYTHONHOME', '-u', 'PYTHONPATH',
               '-u', 'PYTHONSTARTUP', '-u', 'PYTHONINSPECT', '/usr/bin/python3', '-I', '-B', '-c', remote]
    with (HERE / 'delivery/payload.tar').open('rb') as payload, (HERE / (label + '.stdout')).open('xb') as stdout, (HERE / (label + '.stderr')).open('xb') as stderr:
        result = subprocess.run(command, stdin=payload, stdout=stdout, stderr=stderr)
else:
    assert args.sealed_inputs_sha256 and len(args.sealed_inputs_sha256) == 64
    assert json.loads((HERE / 'stage.json').read_text())['returncode'] == 0
    setup_review = json.loads((HERE / 'setup-review.json').read_text())
    assert setup_review['status'] == 'passed'
    assert setup_review['measurement_seal_sha256'] == args.sealed_inputs_sha256
    assert setup_review['transfer_manifest_sha256'] == sha(HERE / 'collections/setup/transfer-manifest.json')
    # SSH runs synchronously so every transport failure is retained. No tmux
    # session, daemon, retry, analysis, or extra sample is created here.
    command = [SSH, HOST, '--', '/usr/bin/env', '-u', 'PYTHONHOME', '-u', 'PYTHONPATH',
               '-u', 'PYTHONSTARTUP', '-u', 'PYTHONINSPECT', '/usr/bin/python3', '-I', '-B', ROOT + '/controller/driver.py',
               '--run-phase', args.launch_phase, '--sealed-inputs-sha256', args.sealed_inputs_sha256]
    with (HERE / (label + '.stdout')).open('xb') as stdout, (HERE / (label + '.stderr')).open('xb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr)
record.update(returncode=result.returncode, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              stdout_sha256=sha(HERE / (label + '.stdout')), stderr_sha256=sha(HERE / (label + '.stderr')))
record_path.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
raise SystemExit(result.returncode)
