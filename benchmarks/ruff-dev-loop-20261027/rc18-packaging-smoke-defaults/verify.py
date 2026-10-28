"""Verify the native smoke outcomes and optionally match both wrapper excerpts to Git source."""
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

here=Path(__file__).resolve().parent
ap=argparse.ArgumentParser()
ap.add_argument('--packaging-git',type=Path)
args=ap.parse_args()
def sha(data):return hashlib.sha256(data).hexdigest()
base='4649b236138f62be1177a4205824931798ba2361'
new='73737405d03f7c9113774ab98400bd33312d26d8'
with tarfile.open(here/'native-streams.tar.gz') as tar:
    files={m.name:tar.extractfile(m).read() for m in tar.getmembers()}
assert len(files)==22
bindings=json.loads(files['inputs.json'])
for f in ('candidate.sh','parent.sh','worker.py'):
    assert sha(files[f])==bindings[f]
if args.packaging_git:
    for name,rev in [('parent',base),('candidate',new)]:
        data=subprocess.check_output(['git','-C',args.packaging_git,'show',rev+':scripts/smoke-test-release.sh'])
        a=data.index(b'smoke_crate="$smoke_root/crate"');b=data.index(b'# Linking a Wasm executable',a)
        assert b'#!/usr/bin/env bash\nset -euo pipefail\n'+data[a:b]==files[name+'.sh']
rows=json.loads(files['results.json'])
assert len(rows)==5
expect={('parent','released',17):0,('parent','candidate',18):101,('candidate','released',17):0,('candidate','candidate',18):0,('candidate','released',18):101}
bins={'released':'4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3','candidate':'cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8'}
for r in rows:
    key=(r['script'],r['cargo'],r['revision']);assert expect.pop(key)==r['status']
    assert r['cargo_sha256']==bins[r['cargo']] and r['driver']=='618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'
    label='-'.join(map(str,key))
    err=files[label+'/stderr']
    assert sha(err)==r['stderr']
    if r['status']==0:
        for name,value in [('defaults-rustc-args','enabled'),('disabled-rustc-args','disabled')]:
            assert files[label+'/'+name].decode().splitlines()==r[name]==[value]
        assert err.count(b'Finished `dev` profile')==2
    else:
        reason=b'Ohm defaults missing' if key[0]=='parent' else b'unexpected proc-macro cache setting'
        assert reason in err
assert not expect
print('5 released/candidate smoke cases, 3 successful enabled/disabled builds, 2 intentional rejections')

