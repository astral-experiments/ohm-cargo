"""Route the frozen replacement wall study with separately published native and CI evidence."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

here=Path(__file__).resolve().parent
root=here.parent
key='rc17-composed-early-wall-plan-v3c'
packet=root/key
mode=sys.argv[1];assert len(sys.argv)==2 or mode=='verify' and len(sys.argv)==3
assert mode in ('install','bind-catalog','admit','admission','idle','score','status','verify')

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def data(value):
    return json.dumps(value,sort_keys=True,indent=2).encode()+b'\n'

refs=read(root/'published-20261027-corrected-cohort-refs.json')
ref=refs[key]
assert re.fullmatch('[0-9a-f]{40}',ref)
digest=sha(packet/'SHA256SUMS')
subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=packet,check=True)
repo=Path('/home/dev-user/code/oss/ohm-ruff-whole-extern-skip-20261027')
rel=f'benchmarks/ruff-dev-loop-20261027/{key}/SHA256SUMS'
assert subprocess.check_output(['git','show',ref+':'+rel],cwd=repo)==(packet/'SHA256SUMS').read_bytes()
payload=b''
if mode=='install':
    buffer=io.BytesIO()
    names=[line.split('  ',1)[1] for line in (packet/'SHA256SUMS').read_text().splitlines()]+['SHA256SUMS']
    assert {f.name for f in packet.iterdir()}==set(names)
    with tarfile.open(fileobj=buffer,mode='w:gz') as bundle:
        for n in sorted(names):
            assert Path(n).name==n and (packet/n).is_file() and not (packet/n).is_symlink()
            bundle.add(packet/n,arcname=n,recursive=False)
    payload=buffer.getvalue()
elif mode=='bind-catalog':
    payload=(here/'wall-v3c-catalog-binding.json').read_bytes()
    bundle=json.loads(payload)
    assert bundle['catalog']['plan_ref']==ref and bundle['catalog']['plan_manifest']==digest
    assert all(bundle['catalog'][name] in refs.values() for name in ('catalog_protocol_ref','catalog_result_ref'))
elif mode=='verify':
    solver=sys.argv[2] if len(sys.argv)==3 else 'verify_result.py';assert re.fullmatch(r'[a-zA-Z0-9_.-]+\.py',solver) and sha(packet/solver)==sha(packet/'verify_result.py');payload=data({'verifier_file':solver})
elif mode=='score':
    subprocess.run([sys.executable,'-IB',str(here/'prepare-wall-v3c.py'),'recheck-score'],check=True)
    payload=(here/'wall-v3c-score-binding.json').read_bytes()
    bundle=json.loads(payload)
    assert bundle['publication']['plan_ref']==ref and bundle['publication']['admission_ref']==refs['rc17-composed-wall-admission-v3c']
    assert bundle['publication']['catalog_ref'] in refs.values()
    assert not (here/'wall-v3c-score.json').exists()

cmd=['dbox','ssh','charlie-ohm-c5-check-1025','--no-tmux','--','/usr/bin/python3','-IB','-c',(here/'wall-h5-v3c.py').read_text(),mode,ref,digest]
out=subprocess.run(cmd,input=payload,capture_output=True)
log=here/f'wall-v3c-{mode}.stderr'
log.write_bytes(out.stderr)
if out.returncode:
    sys.stderr.buffer.write(out.stderr[-1800:])
    sys.exit(out.returncode)
body=json.loads(out.stdout)
if mode=='admission':
    assert isinstance(body,dict) and {'admission.json','ci.json','catalog-publication.json','bootstrap-completion.json','root-native-witness.json','provenance.json'}<=set(body)
    private=here/'wall-v3c-admission-material.json';canonical=data(body)
    if private.exists():assert private.read_bytes()==canonical
    else:
        with private.open('xb') as f:f.write(canonical)
    raw=base64.b64decode(body['admission.json']['bytes_b64'],validate=True);assert hashlib.sha256(raw).hexdigest()==body['admission.json']['sha256']
    body=json.loads(raw);output=raw
else:output=out.stdout
dest=here/f'wall-v3c-{mode}.json'
if mode not in ('status','idle') and dest.exists():
    assert dest.read_bytes()==output
else:
    dest.write_bytes(output)
if mode=='admission':
    print(json.dumps(dict(admission=sha(dest),bytes=len(out.stdout),registered_outputs=len(body['native']['allowed']),scored_commands=body['scored_commands'])))
else:
    print(json.dumps(body,sort_keys=True))
