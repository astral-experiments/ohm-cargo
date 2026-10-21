#!/usr/bin/env python3
"""Publish verified workspace-inheritance-stack180 evidence from a fresh task-owned remote Git repository."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'work/pr-evidence/workspace-inheritance-stack180'
MANIFEST = ROOT / 'work/pr-evidence/workspace-inheritance-stack180-manifest.json'
expected = json.loads(MANIFEST.read_text())
data = (PACKAGE / 'SHA256SUMS').read_bytes()
assert 'SHA256SUMS' not in expected
expected['SHA256SUMS'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
assert {str(path.relative_to(PACKAGE)) for path in PACKAGE.rglob('*') if path.is_file()} == set(expected)
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w') as archive:
    for name, item in sorted(expected.items()):
        data = (PACKAGE / name).read_bytes()
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
        member = tarfile.TarInfo(name)
        member.size = len(data)
        member.mode = 0o644
        member.mtime = 0
        archive.addfile(member, io.BytesIO(data))

remote = r'''
import hashlib,json,subprocess,sys,tarfile
from pathlib import Path
expected=json.loads(sys.argv[1])
root=Path('/tmp/ohm-hillclimb-20261021-workspace-inheritance-stack180-evidence-publication')
repo=root/'repo'
url='https://github.com/astral-sh/ohm-cargo.git'
branch='charlie/uv-ohm-workspace-inheritance-stack180-evidence-20261021'
ref='refs/heads/'+branch
prefix='benchmarks/uv-dev-loop-20261021/workspace-inheritance-stack180/'
auth=['-c','credential.helper=','-c','credential.helper=!gh auth git-credential']
identity=['-c','user.name=Charlie Marsh','-c','user.email=crmarsh416@gmail.com','-c','commit.gpgsign=false']
def run(args,check=True):
    result=subprocess.run(args,capture_output=True)
    if check and result.returncode:
        print(json.dumps({'failed_command':args,'returncode':result.returncode,'stderr':result.stderr.decode(errors='replace')}),file=sys.stderr)
        raise RuntimeError('command failed')
    return result
def absent():
    result=run(['git',*auth,'ls-remote','--exit-code',url,ref],check=False)
    assert result.returncode==2 and not result.stdout, 'evidence branch must be absent'
info=json.loads(run(['gh','api','repos/astral-sh/ohm-cargo']).stdout)
assert info['private'] and info['permissions']['push']
absent()
assert root.parent.resolve()==root.parent and root.parent.is_dir()
assert not root.exists(), 'fresh task-owned evidence publication directory required'
artifact=repo/prefix
artifact.mkdir(parents=True)
seen=set()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
    for member in archive:
        assert member.isfile() and member.name in expected and member.name not in seen
        assert not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
        data=archive.extractfile(member).read()
        item=expected[member.name]
        assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
        path=artifact/member.name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data);path.chmod(0o644);seen.add(member.name)
assert seen==set(expected)
verification={'publication_files_verified':len(expected),'all_transferred_sha256_verified':True}
run(['git','init','--quiet','--initial-branch='+branch,str(repo)])
def git(*args):
    return run(['git','-C',str(repo),'-c','core.autocrlf=false',*identity,*args]).stdout
git('add','--',prefix)
entries=git('ls-files','--stage','-z').split(b'\0')
blob_count=0
for entry in entries:
    if not entry: continue
    metadata,path=entry.split(b'\t',1)
    mode,oid,stage=metadata.decode().split();path=path.decode()
    assert mode=='100644' and stage=='0' and path.startswith(prefix)
    name=path.removeprefix(prefix);assert name in expected
    data=git('cat-file','blob',oid)
    assert len(data)==expected[name]['bytes'] and hashlib.sha256(data).hexdigest()==expected[name]['sha256']
    blob_count+=1
assert blob_count==len(expected)
git('commit','--quiet','-m','Record uv workspace-inheritance-stack180 dev-loop benchmark evidence')
commit=git('rev-parse','HEAD').decode().strip()
tree=git('rev-parse','HEAD^{tree}').decode().strip()
assert not git('status','--porcelain')
assert git('rev-list','--parents','-n','1','HEAD').decode().split()==[commit]
absent()
push=run(['git','-C',str(repo),*auth,'push',url,'HEAD:'+ref])
published=run(['git',*auth,'ls-remote','--exit-code',url,ref]).stdout.decode().split()
assert published==[commit,ref]
record={
 'repository':url,'private':True,'branch':branch,'commit':commit,'tree':tree,
 'commit_url':'https://github.com/astral-sh/ohm-cargo/commit/'+commit,
 'artifact_url':'https://github.com/astral-sh/ohm-cargo/tree/'+commit+'/'+prefix.rstrip('/'),
 'artifact_prefix':prefix,'verified_git_blobs':blob_count,'independent_root_commit':True,
 'non_force_push_verified':True,'remote_root':str(root),
 'sha256sums_sha256':expected['SHA256SUMS']['sha256'],
 'archive_sha256':expected['raw-results.tar.gz']['sha256'],'verification':verification,
 'commit_identity':git('show','-s','--format=%an <%ae>%n%cn <%ce>%n%aI%n%cI','HEAD').decode().strip(),
 'push_stdout':push.stdout.decode(),'push_stderr':push.stderr.decode(),
}
(root/'publication.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
'''
helper = '/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh'
result = subprocess.run([helper, 'charlie-oss-5', '--', 'python3', '-c', remote, json.dumps(expected, separators=(',', ':'))], input=buffer.getvalue(), capture_output=True)
folder = Path(__file__).resolve().parent
(folder / 'evidence-publication.stdout').write_bytes(result.stdout)
(folder / 'evidence-publication.stderr').write_bytes(result.stderr)
if result.returncode:
    sys.stderr.buffer.write(result.stderr)
    sys.stdout.buffer.write(result.stdout)
    raise SystemExit(result.returncode)
record = json.loads(result.stdout)
record['local_manifest'] = str(MANIFEST)
(folder / 'evidence-publication.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
