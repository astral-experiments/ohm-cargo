"""Repeat the ordinary workspace check in the private home warmed by edited.py."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
from tempfile import TemporaryDirectory

ap = argparse.ArgumentParser(description=__doc__)
for name in ['root','home','target','shared','ruff','out']:
    ap.add_argument('--'+name,required=True,type=Path)
ap.add_argument('--cpu',default='16-19')
ap.add_argument('--edited-results',type=Path)
ap.add_argument('--seed',default=897215,type=int)
a=ap.parse_args()
a.out.mkdir()
assert ((a.edited_results or a.root)/'pairs.csv').exists()
env=dict(os.environ,RUSTUP_HOME=str(a.root/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(a.home),
         CARGO_TARGET_DIR=str(a.target),CARGO_BUILD_BUILD_DIR=str(a.shared),CARGO_BUILD_JOBS='6',
         CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',
         CARGO_TERM_COLOR='never',LC_ALL='C.UTF-8',
         SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/etc/ssl/certs')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.ruff,text=True).strip()=='93526150df078af7dd8fc4226cdcc469539d2001'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=a.ruff)
real=a.root/'runtime/bin/cargo'
check=['check','--locked','--offline']

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def choose(arm):
    subject=a.root/arm
    if not real.samefile(subject):
        nxt=real.with_name('cargo.swap')
        os.link(subject,nxt)
        nxt.replace(real)

def run(arm,args,*,count=False):
    choose(arm)
    with TemporaryDirectory(dir=a.root) as td:
        cmd=['taskset','-c',a.cpu,'cargo','+ohm',*args]
        proc=subprocess.run(cmd,cwd=a.ruff,env=dict(env,SAMPLE=td,TRACE_CHILDREN='yes' if count else 'no'),capture_output=True)
        assert proc.returncode==0,proc.stderr.decode(errors='replace')
        assert b'Blocking waiting' not in proc.stderr
        if count:
            assert not any(s.strip().startswith((b'Compiling ',b'Checking ')) for s in proc.stderr.splitlines())
            profile,=Path(td).glob('count.*')
            data=profile.read_bytes()
            assert Path(re.search(rb'^cmd:\s+(\S+)',data,re.M)[1].decode()).name=='cargo'
            return int(re.search(rb'^summary: (\d+)$',data,re.M)[1])
        return proc.stdout

def artifacts(arm):
    data=run(arm,check+['--message-format=json'])
    units=[j for j in map(json.loads,data.splitlines()) if j['reason']=='compiler-artifact']
    assert len(units)==520 and all(j['fresh'] for j in units)
    metas={Path(f) for j in units for f in j['filenames'] if f.endswith('.rmeta')}
    apis={p for d in [a.target,a.shared] for p in d.rglob('*.public-api-hash')}
    return dict(roster=sorted((j['package_id'],j['target']['name'],j['target']['kind'],j['profile']['test']) for j in units),
                metadata={str(p):sha(p) for p in sorted(metas)},api={str(p):sha(p) for p in sorted(apis)})

def inventory():
    return {v:{p.name:(p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns)
            for p in (a.home/('.ohm-registry-json-'+v)).iterdir()} for v in ['v1','v2']}

reference=artifacts('parent')
assert artifacts('candidate')==reference
initial=inventory()
flips=list(range(12))
random.Random(a.seed).shuffle(flips)
with (a.out/'pairs.csv').open('x',newline='') as f:
    writer=csv.writer(f);writer.writerow(['pair','first_arm','parent_ir','candidate_ir'])
    for i,flip in enumerate(flips):
        order=['candidate','parent'] if flip%2 else ['parent','candidate']
        counts={arm:run(arm,check,count=True) for arm in order}
        writer.writerow([i,order[0],counts['parent'],counts['candidate']]);f.flush()
        print(i,order[0],counts['parent'],counts['candidate'],flush=True)
assert inventory()==initial
assert artifacts('parent')==reference==artifacts('candidate')
fixture=['metadata','--format-version=1','--locked','--offline']
metadata={arm:json.loads(run(arm,fixture)) for arm in ['parent','candidate']}
assert metadata['parent']==metadata['candidate']
body=metadata['parent']
receipt={'units':len(reference['roster']),'metadata_files':len(reference['metadata']),'api_files':len(reference['api']),
         'cargo_metadata_packages':len(body['packages']),'resolved_nodes':len(body['resolve']['nodes']),
         'cargo_metadata_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
         'registry_cache_counts':{v:len(f) for v,f in initial.items()},
         'stable_cache_records':True,'seed':a.seed}
(a.out/'validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
