"""Measure Cargo and rustc together for the sealed parser holdout."""
import argparse
from contextlib import contextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import subprocess

ap=argparse.ArgumentParser(description=__doc__)
for arg in ['pool','results','ruff','parent','candidate','toolchain','registry','patch']:
    ap.add_argument('--'+arg,required=True,type=Path)
ap.add_argument('--seed',default=971531,type=int)
ap.add_argument('--cpu',default='8-15')
a=ap.parse_args()
a.pool.mkdir(mode=0o700)
a.results.mkdir()
assert hashlib.sha256(a.patch.read_bytes()).hexdigest()=='8e26eef22165dae5bd873943c1b7d05123392d285d0754cd757d4007b49b89fa'
q=a.pool
def clean():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.ruff).strip()==b'93526150df078af7dd8fc4226cdcc469539d2001'
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=a.ruff)
clean()
tool=q/'rustup/toolchains/ohm'
shutil.copytree(a.toolchain,tool,symlinks=True)
for p in ['target','shared','runtime/bin','registry-home']:
    (q/p).mkdir(parents=True)
shutil.copytree(a.registry/'registry',q/'registry-home/registry',symlinks=True)
binary=q/'runtime/bin/cargo'
screen=tool/'bin/cargo'
screen.unlink()
screen.write_text('#!/bin/sh\nexec valgrind --tool=callgrind --trace-children="$OHM_TRACE" --cache-sim=no --branch-sim=no --log-file="$SAMPLE/log.%p" --callgrind-out-file="$SAMPLE/count.%p" '+shlex.quote(str(binary))+' "$@"\n')
screen.chmod(0o755)
for arm,path in [('parent',a.parent),('candidate',a.candidate)]:shutil.copy2(path,q/arm)
env=dict(os.environ,RUSTUP_HOME=str(q/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',LC_ALL='C.UTF-8',
         CARGO_TARGET_DIR=str(q/'target'),CARGO_BUILD_BUILD_DIR=str(q/'shared'),CARGO_HOME=str(q/'registry-home'),
         CARGO_BUILD_JOBS='6',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',
         SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/etc/ssl/certs')
for f in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','OHM_FRONTEND_SCHEDULING_SCREEN'):env.pop(f,None)
@contextmanager
def reversed_edit():
    subprocess.run(['git','apply','--reverse','--whitespace=nowarn',str(a.patch)],cwd=a.ruff,check=True)
    try:yield
    finally:
        subprocess.run(['git','apply','--whitespace=nowarn',str(a.patch)],cwd=a.ruff,check=True)
        clean()
def run(arm,tag,prime=False):
    if not binary.exists() or not binary.samefile(q/arm):
        temp=binary.with_name('next')
        os.link(q/arm,temp);temp.replace(binary)
    d=q/tag;d.mkdir()
    cmd=['taskset','-c',a.cpu,'cargo','+ohm','check','-p','ruff_python_parser','--locked','--offline','--message-format=json']
    with (d/'stdout').open('wb') as stdout,(d/'stderr').open('wb') as stderr:
        subprocess.run(cmd,cwd=a.ruff,env={**env,'SAMPLE':str(d),'OHM_TRACE':'no' if prime else 'yes'},stdout=stdout,stderr=stderr,check=True)
    assert 'Blocking waiting' not in (d/'stderr').read_text()
    artifacts=[j for j in map(json.loads,(d/'stdout').read_bytes().splitlines()) if j['reason']=='compiler-artifact']
    roster=sorted((j['package_id'],j['target']['name'],j['target']['kind'],j['profile']['test']) for j in artifacts)
    dirty=sorted((j['target']['name'],j['target']['kind']) for j in artifacts if not j['fresh'])
    counts={}
    for f in d.glob('count.*'):
        data=f.read_bytes()
        name=Path(re.search(rb'^cmd:\s+(\S+)',data,re.M)[1].decode()).name
        assert name not in counts,name
        counts[name]=int(re.search(rb'^summary: (\d+)$',data,re.M)[1])
    def digest(files):
        h=hashlib.sha256()
        for f in sorted(set(files)):
            h.update(str(f.relative_to(q)).encode()+b'\0')
            with f.open('rb') as inp:h.update(hashlib.file_digest(inp,'sha256').digest())
        return h.hexdigest()
    metas={Path(f) for j in artifacts for f in j['filenames'] if f.endswith('.rmeta')}
    apis={f for s in ['target','shared'] for f in (q/s).rglob('*.public-api-hash')}
    assert metas and apis
    receipt=dict(roster=hashlib.sha256(json.dumps(roster).encode()).hexdigest(),artifacts=len(roster),dirty=dirty,counts=counts,
                 metas=len(metas),apis=len(apis),meta_digest=digest(metas),api_digest=digest(apis))
    (a.results/(tag+'.json')).write_text(json.dumps(receipt)+'\n')
    return receipt
run('parent','prime',True)
warm=run('parent','warm')
assert warm['dirty']==[] and warm['counts'].keys()=={'cargo'}
snap=q/'checkpoint';snap.mkdir()
for s in ['target','shared']:
    subprocess.run(['cp','-a',q/s,snap/s],check=True)
def restore():
    for s in ['target','shared']:
        subprocess.run(['rsync','-a','--delete','--checksum',str(snap/s)+'/',str(q/s)+'/'],check=True)
flips=list(range(12));random.Random(a.seed).shuffle(flips)
control=None
with (a.results/'pairs.csv').open('w') as stream:
    out=csv.writer(stream);out.writerow(['pair','first_arm','parent_cargo_ir','parent_rustc_ir','candidate_cargo_ir','candidate_rustc_ir'])
    with reversed_edit():
        for n,flip in enumerate(flips):
            arms=['candidate','parent'] if flip%2 else ['parent','candidate']
            r={}
            for arm in arms:
                restore();v=run(arm,f'{n:02}-{arm}')
                assert len(v['dirty'])==1 and v['dirty'][0][0]=='ruff_python_parser' and v['roster']==warm['roster'] and v['counts'].keys()=={'cargo','rustc'},v
                sig=[v[k] for k in ('dirty','roster','metas','apis','meta_digest','api_digest')]
                if control is None:control=sig
                assert sig==control,sig
                r[arm]=v['counts']
            vals=[r[a][p] for a in ['parent','candidate'] for p in ['cargo','rustc']]
            out.writerow([n,arms[0],*vals]);stream.flush()
            print(n,arms[0],*vals,round(100*(1-sum(vals[2:])/sum(vals[:2])),3),flush=True)
