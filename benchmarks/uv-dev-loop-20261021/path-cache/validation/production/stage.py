#!/usr/bin/env python3
import datetime
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / 'work/path-cache-validation'
REMOTE = '/tmp/ohm-hillclimb-20261021/path-cache-validation'
BAKED = '/home/dev-user/Documents/Codex/2026-10-20/i-want-you-to-hillclimb-on'
HELPER = '/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


source = LOCAL / 'harness-source.tar'
with source.open('xb') as stream:
    subprocess.run(['git', '-C', str(ROOT / 'work/ohm-cargo'), 'archive', '--format=tar',
                    'c692e3c07d295e596b9f10eb4b1c89bb498caf68'], stdout=stream, check=True)
files = {
    'run_remote.py': LOCAL / 'run_remote.py',
    'tests.json': LOCAL / 'tests.json',
    'harness-source.tar': source,
    'testsuite-af6fdb42b18789ae': ROOT / 'work/cargo-build/release/deps/testsuite-af6fdb42b18789ae',
}
for variant, name in [('baseline', 'cargo-pr175'), ('candidate', 'cargo-pr175-path-cache')]:
    files['binaries/cargo-' + variant] = ROOT / 'work/production-build/results' / name
    for suffix in ('.build.json', '.strip.json'):
        files['metadata/' + name + suffix] = ROOT / 'work/production-build/results' / (name + suffix)
for name in ('pr175.source.patch', 'pr175-path-cache.source.patch'):
    files['metadata/' + name] = ROOT / 'work/production-build/results' / name
manifest = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'remote_root': REMOTE, 'baked_root': BAKED,
            'files': {name: sha(path) for name, path in files.items()}}
(LOCAL / 'inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
files['inputs.json'] = LOCAL / 'inputs.json'
code = r'''
import datetime,hashlib,json,os,pathlib,shutil,sys,tarfile
root=pathlib.Path('/tmp/ohm-hillclimb-20261021/path-cache-validation')
baked=pathlib.Path('/home/dev-user/Documents/Codex/2026-10-20/i-want-you-to-hillclimb-on')
assert not root.exists() and not root.is_symlink()
assert not baked.exists() and not baked.is_symlink()
assert os.getuid()==1000
root.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as stream:
    stream.extractall(root,filter='data')
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
manifest=json.loads((root/'inputs.json').read_text())
for name,expected in manifest['files'].items():
    assert sha(root/name)==expected,name
created=[]
for path in [pathlib.Path('/home/dev-user/Documents'),pathlib.Path('/home/dev-user/Documents/Codex'),pathlib.Path('/home/dev-user/Documents/Codex/2026-10-20'),baked]:
    assert not path.exists() and not path.is_symlink(),str(path)
    path.mkdir(mode=0o755)
    created.append(str(path))
ownership={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'evidence_root':str(root),'baked_root':str(baked),'uid':os.getuid(),'gid':os.getgid(),'created_parent_paths':created,'purpose':'Exact historical PR175 path-cache production CLI validation only; no symlink or namespace.'}
(baked/'.ohm-validation-owner.json').write_text(json.dumps(ownership,indent=2)+'\n')
(root/'ownership.json').write_text(json.dumps(ownership,indent=2)+'\n')
(baked/'work/cargo-build/release/deps').mkdir(parents=True)
(baked/'work/cargo-build/tmp').mkdir()
(baked/'work/ohm-cargo').mkdir()
with tarfile.open(root/'harness-source.tar') as stream:
    stream.extractall(baked/'work/ohm-cargo',filter='data')
runner=baked/'work/cargo-build/release/deps/testsuite-af6fdb42b18789ae'
shutil.copy2(root/'testsuite-af6fdb42b18789ae',runner)
assert sha(runner)==manifest['files']['testsuite-af6fdb42b18789ae']
runner.chmod(0o755)
for name in ['tmp','cargo-home']:(root/name).mkdir()
for name in ['baseline','candidate']:(root/'binaries'/('cargo-'+name)).chmod(0o755)
print(json.dumps({'status':'staged','root':str(root),'baked_root':str(baked),'ownership':ownership,'manifest_sha256':sha(root/'inputs.json')},indent=2))
'''
process = subprocess.Popen([HELPER, 'charlie-oss-4', '--', 'python3', '-c', code],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
with tarfile.open(fileobj=process.stdin, mode='w|') as stream:
    for name, path in files.items():
        stream.add(path, arcname=name, recursive=False)
process.stdin.close()
process.stdin = None
stdout, stderr = process.communicate(timeout=120)
(LOCAL / 'stage.stdout').write_bytes(stdout)
(LOCAL / 'stage.stderr').write_bytes(stderr)
print(stdout.decode()); print(stderr.decode())
raise SystemExit(process.returncode)
