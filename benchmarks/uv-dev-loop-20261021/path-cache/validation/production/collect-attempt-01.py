#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
HELPER = '/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh'
code = r'''
import datetime,hashlib,json,os,pathlib,sys,tarfile
root=pathlib.Path('/tmp/ohm-hillclimb-20261021/path-cache-validation')
baked=pathlib.Path('/home/dev-user/Documents/Codex/2026-10-20/i-want-you-to-hillclimb-on')
report=json.loads((root/'attempt-candidate/report.json').read_text())
assert report['status']=='passed' and report['summaries']==[['93','0','4','0','4683']]
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
expected=set();rows={}
with tarfile.open(root/'harness-source.tar') as archive:
 for item in archive:
  path=baked/'work/ohm-cargo'/item.name
  if item.isfile():
   expected.add(item.name);content=archive.extractfile(item).read();actual=sha(path)
   assert actual==hashlib.sha256(content).hexdigest(),item.name
   assert bool(path.stat().st_mode&0o111)==bool(item.mode&0o111),item.name
   rows[item.name]={'sha256':actual,'executable':bool(item.mode&0o111)}
  elif item.issym():
   expected.add(item.name);assert path.is_symlink() and os.readlink(path)==item.linkname,item.name
   rows[item.name]={'symlink':item.linkname}
actual={str(path.relative_to(baked/'work/ohm-cargo')) for path in (baked/'work/ohm-cargo').rglob('*') if path.is_file() or path.is_symlink()}
assert expected==actual,sorted(expected^actual)
proof={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_tree':'c692e3c07d295e596b9f10eb4b1c89bb498caf68','archive_sha256':sha(root/'harness-source.tar'),'tracked_entries':len(rows),'source_unchanged_after_tests':True,'tracked_files_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'uid':os.getuid(),'gid':os.getgid(),'uid_map':pathlib.Path('/proc/self/uid_map').read_text(),'gid_map':pathlib.Path('/proc/self/gid_map').read_text(),'hostname':os.uname().nodename}
(root/'source-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
files={str(path.relative_to(root)):path for path in (root/'attempt-candidate').iterdir() if path.is_file()}
for name in ['run_remote.py','inputs.json','tests.json','ownership.json','source-verification.json','candidate-driver.log']:
 files[name]=root/name
files.update({str(path.relative_to(root)):path for path in (root/'metadata').iterdir() if path.is_file()})
manifest={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{name:{'sha256':sha(path),'bytes':path.stat().st_size} for name,path in sorted(files.items())},'large_immutable_assets_omitted_from_package':{name:expected for name,expected in json.loads((root/'inputs.json').read_text())['files'].items() if name.startswith('binaries/') or name in ['harness-source.tar','testsuite-af6fdb42b18789ae']}}
(root/'evidence-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
files['evidence-manifest.json']=root/'evidence-manifest.json'
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for name,path in sorted(files.items()):archive.add(path,arcname=name,recursive=False)
'''
archive = HERE / 'production-path-cache-correctness.tar'
with archive.open('xb') as output:
    subprocess.run([HELPER, 'charlie-oss-4', '--', 'python3', '-c', code], stdout=output, check=True)
destination = HERE / 'evidence'
destination.mkdir(exist_ok=False)
with tarfile.open(archive) as source:
    source.extractall(destination, filter='data')
manifest = json.loads((destination / 'evidence-manifest.json').read_text())
for name, expected in manifest['files'].items():
    data = (destination / name).read_bytes()
    assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256']
print(json.dumps({'verified_files': len(manifest['files']), 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'report_sha256': manifest['files']['attempt-candidate/report.json']['sha256'],
                  'test_log_sha256': manifest['files']['attempt-candidate/tests.log']['sha256'],
                  'source_proof': json.loads((destination / 'source-verification.json').read_text())}, indent=2))
