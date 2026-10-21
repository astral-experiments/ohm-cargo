#!/usr/bin/env python3
"""Preserve the IR attempt stopped after both raw audits; no sampling or analysis."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = '/tmp/ohm-hillclimb-20261021-inheritance-measurement'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--phase', choices=('ir',), required=True)
parser.add_argument('--sealed-inputs-sha256', required=True)
args = parser.parse_args()
assert len(args.sealed_inputs_sha256) == 64 and set(args.sealed_inputs_sha256) <= set('0123456789abcdef')
operation = 'stage' if args.phase == 'setup' else 'launch-' + args.phase
assert json.loads((HERE / (operation + '.json')).read_text())['returncode'] == 1
binding = json.loads((HERE / 'delivery/binding.json').read_text())
source = json.loads((HERE / 'source-freeze.json').read_text())
for name, digest in source['files'].items():
    assert sha(HERE / name) == digest
destination = HERE / 'collections' / 'ir-failed-postguard'
destination.mkdir(parents=True, exist_ok=False)
remote = r'''
import hashlib,importlib.util,io,json,os,socket,sys,tarfile
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-measurement')
phase,seal,delivery_sha,driver_sha=sys.argv[1:]
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
assert socket.gethostname()=='charlie-oss-2' and os.getuid()==1000
assert root.resolve()==root and root.stat().st_uid==1000
assert sha(root/'delivery.json')==delivery_sha
assert json.loads((root/'ownership.json').read_text())['delivery_sha256']==delivery_sha
script=root/'controller/driver.py';assert sha(script)==driver_sha
spec=importlib.util.spec_from_file_location('inheritance_collection_driver',script)
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
try:
 collection_quiet={'passed':True,'observation':driver.reference('ir').quiet()}
except AssertionError as error:
 collection_quiet={'passed':False,'error':repr(error),'scope':'Read-only preservation, no workload or statistical execution.'}
driver.verify_assets();driver.verify_seal(seal)
status=driver.read(driver.phase_status('ir'))
assert phase=='ir' and status['state']=='failed'
assert status['integrity_complete']==['check','test'] and status['completed']==[]
assert 'AnsiballZ_command.py' in status['error']
assert not driver.phase_status('native').exists()
for workflow in ('check','test'):
 for name in ('analysis.json','analysis-stdout.json','gate.json'):
  assert not (driver.paths('ir',workflow)['output']/name).exists()
def selected():
 paths=[root/name for name in ('delivery.json','ownership.json','delivery-occupancy.json')]
 for directory in ('controller','metadata','logs','benchmark','results'):
  for path in (root/directory).rglob('*'):
   assert not path.is_symlink(),path
   if path.is_dir():continue
   assert path.is_file() and not path.is_symlink(),path
   if path.is_relative_to(root/'controller/binaries'):continue
   paths.append(path)
 return {str(path.relative_to(root)):sha(path) for path in sorted(set(paths))}
files=selected()
# Hash before auditing, then recheck after serialization: the received bytes
# must be the same bytes whose raw groups/profiles passed these audits.
if phase!='setup':
 core=driver.load_module('paired',driver.CORE,driver.CORE_SHA)
 for workflow,seed in driver.STAGES['ir']['plan']:driver.audit_ir(core,workflow,seed)
 if phase=='native':
  for workflow,seed in driver.STAGES['native']['plan']:
   driver.reference('native').audit_complete(core,workflow,seed)
   directory=driver.paths('native',workflow)['output']
   driver.audit_sample_tables(directory,driver.read(directory/'samples.json'),'native')
manifest={'phase':phase,'root':str(root),'seal_sha256':seal,'delivery_sha256':delivery_sha,
          'driver_sha256':driver_sha,'files':files,'terminal_state':'failed','qualifies':False,
          'collection_quiet':collection_quiet,'scope':'Retained IR attempt stopped after both raw audits; no resampling or analysis.'}
data=(json.dumps(manifest,indent=2)+'\n').encode()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 info=tarfile.TarInfo('transfer-manifest.json');info.size=len(data);info.mode=0o644
 archive.addfile(info,io.BytesIO(data))
 for name in files:archive.add(root/name,arcname='remote/'+name,recursive=False)
assert selected()==files
driver.verify_assets();driver.verify_seal(seal)
'''
command = ['/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh', 'charlie-oss-2',
           '--', '/usr/bin/python3', '-I', '-B', '-c', remote, args.phase, args.sealed_inputs_sha256,
           binding['delivery_sha256'], source['files']['driver.py']]
with (destination / 'payload.tar').open('xb') as stdout, (destination / 'transfer.stderr').open('xb') as stderr:
    result = subprocess.run(command, stdout=stdout, stderr=stderr)
(destination / 'transport.json').write_text(json.dumps({'returncode': result.returncode,
    'archive_sha256': sha(destination / 'payload.tar'), 'stderr_sha256': sha(destination / 'transfer.stderr')}, indent=2) + '\n')
assert result.returncode == 0
seen = set()
with tarfile.open(destination / 'payload.tar', 'r:') as archive:
    first = archive.next()
    assert first.name == 'transfer-manifest.json' and first.isfile()
    data = archive.extractfile(first).read()
    manifest = json.loads(data)
    assert manifest['phase'] == args.phase and manifest['root'] == ROOT
    assert manifest['seal_sha256'] == args.sealed_inputs_sha256
    assert manifest['delivery_sha256'] == binding['delivery_sha256']
    assert manifest['driver_sha256'] == source['files']['driver.py']
    (destination / first.name).write_bytes(data)
    for member in iter(archive.next, None):
        name = Path(member.name)
        assert member.isfile() and not name.is_absolute() and '..' not in name.parts
        assert name.parts[0] == 'remote' and member.name not in seen
        relative = str(name.relative_to('remote'))
        assert relative in manifest['files']
        seen.add(member.name)
        archive.extract(member, destination, filter='data')
        assert sha(destination / name) == manifest['files'][relative]
assert seen == {'remote/' + name for name in manifest['files']}
copied = destination / 'remote'
assert sha(copied / 'delivery.json') == binding['delivery_sha256']
assert sha(copied / 'controller/measurement-seal.json') == args.sealed_inputs_sha256
assert sha(copied / 'controller/source-freeze.json') == sha(HERE / 'source-freeze.json')
for relative, digest in json.loads((copied / 'controller/assets.json').read_text())['files'].items():
    if relative in manifest['files']:
        assert sha(copied / relative) == digest
for filename, digest in json.loads((copied / 'controller/measurement-seal.json').read_text())['file_sha256'].items():
    path = Path(filename)
    if path.is_relative_to(ROOT):
        relative = str(path.relative_to(ROOT))
        if relative in manifest['files']:
            assert sha(copied / relative) == digest
receipt = {'status': 'preserved', 'qualifies': False, 'phase': args.phase, 'files': len(seen),
           'transfer_manifest_sha256': sha(destination / 'transfer-manifest.json'),
           'measurement_seal_sha256': args.sealed_inputs_sha256,
           'scope': 'Preserved failed attempt; all transferred bytes and available static seal entries verified. No qualification, analysis or sampling.'}
(destination / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
