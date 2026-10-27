"""Replay one Ruff edit against an installed Ohm toolchain in a clean, pinned worktree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('worktree',type=Path)
p.add_argument('edit',choices=['doc','parser'])
p.add_argument('mode',choices=['build','test'])
p.add_argument('--target',type=Path,required=True)
p.add_argument('--shared-build',type=Path,required=True)
p.add_argument('--expect-driver',help='Require this release rustc driver SHA-256.')
p.add_argument('--expect-cargo',help='Require this Cargo binary SHA-256.')
p.add_argument('--trace-edit',type=Path,help='Record actual execs in a new private directory in place of timing the edit.')
a=p.parse_args()
repo=a.worktree.resolve(); target=a.target.resolve(); shared=a.shared_build.resolve()
if target.is_relative_to(shared) or shared.is_relative_to(target):
    p.error('target and shared-build must be separate, non-overlapping directories')
here=Path(__file__).resolve().parent
plan=json.loads((here/'plan.json').read_bytes())
patch=here/'fixtures'/({'doc':'private-helper-doc.patch','parser':'parser-tstring.patch'}[a.edit])
assert hashlib.sha256(patch.read_bytes()).hexdigest()==plan['edits'][a.edit]['patch']
env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(shared),CARGO_BUILD_JOBS='8',
         CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',GIT_OPTIONAL_LOCKS='0')
cmd=['cargo','+ohm',a.mode]+(['--no-run'] if a.mode=='test' else [])+['--locked','--offline']

sysroot=Path(subprocess.check_output(['rustc','+ohm','--print','sysroot'],env=env,text=True).strip())
driver,=list((sysroot/'lib').glob('librustc_driver-*.so'))
def digest(path):
    with path.open('rb') as reader:
        return hashlib.file_digest(reader,'sha256').hexdigest()
toolchain={'rustc_driver':digest(driver),'cargo':digest(sysroot/'bin/cargo')}
for expected,actual in [(a.expect_driver,toolchain['rustc_driver']),(a.expect_cargo,toolchain['cargo'])]:
    if expected and expected!=actual:p.error(f'Expected tool SHA-256 {expected}, found {actual}')

def git(*args):
    return subprocess.check_output(['git','--no-optional-locks',*map(str,args)],cwd=repo,env=env,text=True).strip()

def ordinary(trace=None):
    call=cmd
    if trace is not None:
        trace.mkdir(mode=0o700)
        call=['strace','-ff','-qq','-s','65536','-e','trace=execve,execveat','-o',str(trace.resolve()/'exec'),*cmd]
    start=time.monotonic_ns()
    subprocess.run(call,cwd=repo,env=env,check=True)
    return (time.monotonic_ns()-start)/1e9 if trace is None else None

def verify(edited):
    result=subprocess.check_output([*cmd,'--message-format=json'],cwd=repo,env=env)
    rows=[json.loads(line) for line in result.splitlines() if line.startswith(b'{')]
    units=[r for r in rows if r['reason']=='compiler-artifact']
    assert rows[-1]['success'] and len(units)==(501 if a.mode=='build' else 619) and all(r['fresh'] for r in units)
    ruff,={r['executable'] for r in units if r['target']['name']=='ruff' and r['target']['kind']==['bin'] and r['executable'] and not r['profile']['test']}
    def probe(flags,data):
        proc=subprocess.run([ruff,'check','--isolated','--no-cache','--output-format','json',*flags,'-'],input=data,cwd=repo,env=env,capture_output=True)
        assert proc.returncode==1 and not proc.stderr
        return json.loads(proc.stdout)
    message='Bytes literal cannot be mixed with non-bytes literals' if edited and a.edit=='parser' else 'Cannot mix t-string literals with string or bytes literals'
    assert [r['message'] for r in probe(['--target-version','py314'],b"t'first' b'second'\n")]==[message]
    sample=b'from dataclasses import dataclass, field\n@dataclass\nclass C:\n    a: list[int] = field(default=[])\n    b: list[int] = field(default_factory=list)\n    c: list[int] = []\n'
    assert [(r['code'],r['location']['row'],r['location']['column']) for r in probe(['--preview','--select','RUF008','--stdin-filename','case.py'],sample)]==[('RUF008',4,34),('RUF008',6,20)]
    return len(units)

assert git('rev-parse','HEAD')==plan['pin'] and not git('status','--porcelain')
assert git('rev-parse','--absolute-git-dir')!=git('rev-parse','--path-format=absolute','--git-common-dir')
index=Path(git('rev-parse','--path-format=absolute','--git-path','index'))
index_hash=hashlib.sha256(index.read_bytes()).digest()
names=[row.split('\t',2)[2] for row in git('apply','--numstat',patch).splitlines()]
assert all(n.startswith('crates/') and '..' not in Path(n).parts for n in names)
originals={n:((repo/n).read_bytes(),(repo/n).stat()) for n in names}
ordinary();ordinary();verify(False)
git('apply','--reverse','--check',patch)
git('apply','--reverse','--whitespace=nowarn',patch)
try:
    elapsed=ordinary(a.trace_edit);noop=ordinary();units=verify(True)
finally:
    for name,(content,stat) in originals.items():
        path=repo/name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        path.chmod(stat.st_mode & 0o777);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert not git('status','--porcelain') and hashlib.sha256(index.read_bytes()).digest()==index_hash
ordinary();verify(False)
print(json.dumps(dict(edit=a.edit,command=cmd,toolchain=toolchain,edit_seconds=elapsed,immediate_noop_seconds=noop,fresh_units=units,source_restored=True)))
