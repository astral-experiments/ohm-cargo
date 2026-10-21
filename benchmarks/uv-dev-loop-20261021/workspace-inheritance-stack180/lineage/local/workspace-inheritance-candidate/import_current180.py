import hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
remote=r"""
import subprocess,sys
from pathlib import Path
owned=Path('/tmp/ohm-hillclimb-20261021/workspace-inheritance-source')
assert not owned.exists();owned.mkdir()
repo=owned/'repo'
source=Path('/tmp/ohm-hillclimb-20261021/path-cache-code-publication/repo')
base='19718e6d1637244ffbb193334f50bae3ffca1be5'
head='c40676e264501bc8a93095d3a273a1c300b80875'
tree='0a392258c801cff734d223a3f9af73d5b5a4e3c0'
ref='refs/heads/current-stack-180-input'
subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(source),str(repo)],check=True)
def git(*args):
 return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True).stdout
auth=['-c','credential.helper=','-c','credential.helper=!gh auth git-credential']
git(*auth,'fetch','--quiet','--depth=64','https://github.com/astral-sh/ohm-cargo.git',head)
assert git('rev-parse','FETCH_HEAD').decode().strip()==head
assert git('rev-parse',head+'^{tree}').decode().strip()==tree
git('merge-base','--is-ancestor',base,head)
git('update-ref',ref,head)
bundle=owned/'current-stack-180.bundle'
git('bundle','create',str(bundle),ref,'^'+base)
sys.stdout.buffer.write(bundle.read_bytes())
"""
result=subprocess.run(['/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh','charlie-oss-4','--','python3','-c',remote],capture_output=True)
out=root/'work/workspace-inheritance-candidate'
(out/'import.stderr').write_bytes(result.stderr)
if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
p=out/'current-stack-180.bundle';assert not p.exists();p.write_bytes(result.stdout)
record={'bundle':str(p),'bytes':len(result.stdout),'sha256':hashlib.sha256(result.stdout).hexdigest(),'head':'c40676e264501bc8a93095d3a273a1c300b80875','tree':'0a392258c801cff734d223a3f9af73d5b5a4e3c0','prerequisite':'19718e6d1637244ffbb193334f50bae3ffca1be5','repository':'https://github.com/astral-sh/ohm-cargo.git','remote_owned_root':'/tmp/ohm-hillclimb-20261021/workspace-inheritance-source'}
(out/'import.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
