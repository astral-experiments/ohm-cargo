#!/usr/bin/env python3
"""Publish the reviewed shared-workspace-dependency patch from exact PR180."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
patch = ROOT / 'work/workspace-inheritance-candidate/share-workspace-dependencies.patch'
data = patch.read_bytes()
assert hashlib.sha256(data).hexdigest() == 'cbace02bcebcce462e5912e832ade58e30822e0e83cece47039636fdfe58e4c9'
remote = r'''
import hashlib,json,subprocess,sys,os,socket,datetime
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-code-publication')
repo=root/'repo'
url='https://github.com/astral-sh/ohm-cargo.git'
branch='charlie/uv-share-workspace-dependencies'
ref='refs/heads/'+branch
base='c40676e264501bc8a93095d3a273a1c300b80875'
tree_expected='c4178b67e0b3a64a12b9b58f84b97323b99d734e'
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
    assert result.returncode==2 and not result.stdout, 'code branch must be absent'
info=json.loads(run(['gh','api','repos/astral-sh/ohm-cargo']).stdout)
assert info['private'] and info['permissions']['push']
absent()
assert root.parent.resolve()==root.parent and root.parent.is_dir()
assert not root.exists(), 'fresh task-owned code publication directory required'
assert os.getuid()==1000 and socket.gethostname()=='charlie-oss-5'
assert root.parent==Path('/tmp') and root.parent.stat().st_uid==0
root.mkdir(mode=0o700)
(root/'ownership.json').write_text(json.dumps({'root':str(root),'uid':os.getuid(),'purpose':'Reviewed current180 shared-workspace-dependency source publication'},indent=2)+'\n')
data=sys.stdin.buffer.read()
digest=hashlib.sha256(data).hexdigest()
assert digest=='cbace02bcebcce462e5912e832ade58e30822e0e83cece47039636fdfe58e4c9'
patch=root/'share-workspace-dependencies.patch';patch.write_bytes(data)
run(['git','init','--quiet',str(repo)])
def git(*args):
    return run(['git','-C',str(repo),'-c','core.autocrlf=false',*identity,*args]).stdout
run(['git','-C',str(repo),*auth,'fetch','--quiet','--depth=1',url,base])
git('checkout','--quiet','-b',branch,'FETCH_HEAD')
assert git('rev-parse','HEAD').decode().strip()==base
assert git('rev-parse','HEAD^{tree}').decode().strip()=='0a392258c801cff734d223a3f9af73d5b5a4e3c0'
assert not git('status','--porcelain')
git('apply','--check',str(patch))
git('apply','--index',str(patch))
files=git('diff','--cached','--name-only','-z').decode().strip('\0').split('\0')
assert sorted(files)==['src/workspace/parser/mod.rs']
assert git('write-tree').decode().strip()==tree_expected
assert not git('diff','--name-only')
git('diff','--cached','--check')
git('commit','--quiet','-m','Share inherited workspace dependency maps between members')
commit=git('rev-parse','HEAD').decode().strip()
tree=git('rev-parse','HEAD^{tree}').decode().strip()
assert tree==tree_expected
assert git('rev-list','--parents','-n','1','HEAD').decode().split()==[commit,base]
assert not git('status','--porcelain')
absent()
push=run(['git','-C',str(repo),*auth,'push',url,'HEAD:'+ref])
published=run(['git',*auth,'ls-remote','--exit-code',url,ref]).stdout.decode().split()
assert published==[commit,ref]
record={'published_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repository':url,'private':True,'branch':branch,'base_commit':base,'commit':commit,'tree':tree,
        'commit_url':'https://github.com/astral-sh/ohm-cargo/commit/'+commit,
        'patch_sha256':digest,'files':files,'non_force_push_verified':True,'remote_root':str(root),
        'commit_identity':git('show','-s','--format=%an <%ae>%n%cn <%ce>%n%aI%n%cI','HEAD').decode().strip(),
        'push_stdout':push.stdout.decode(),'push_stderr':push.stderr.decode()}
(root/'publication.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
'''
helper = '/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh'
result = subprocess.run([helper, 'charlie-oss-5', '--', 'python3', '-c', remote], input=data, capture_output=True)
folder = Path(__file__).resolve().parent
(folder / 'code-publication.stdout').write_bytes(result.stdout)
(folder / 'code-publication.stderr').write_bytes(result.stderr)
if result.returncode:
    sys.stderr.buffer.write(result.stderr)
    sys.stdout.buffer.write(result.stdout)
    raise SystemExit(result.returncode)
record = json.loads(result.stdout)
(folder / 'code-publication.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
