"""Compare Cargo frontend policies on real Ruff edits restored from a shared pre-edit checkpoint."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import shutil
import socket
import statistics
import subprocess
import time

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('phase', choices=['screen', 'holdout', 'guard'])
ap.add_argument('--blocks', type=int, required=True)
ap.add_argument('--seed', type=int, required=True)
ap.add_argument('--out', required=True, type=Path)
ap.add_argument('--pool', required=True, type=Path)
ap.add_argument('--ruff', required=True, type=Path)
ap.add_argument('--candidate', type=Path)
ap.add_argument('--parent', type=Path)
ap.add_argument('--timings', action='store_true')
a = ap.parse_args()
assert (a.phase == 'screen') == (a.candidate is None and a.parent is None)
a.out.mkdir()
pool, ruff = a.pool.resolve(), a.ruff.resolve()
pinned = '93526150df078af7dd8fc4226cdcc469539d2001'
git = ['git', '-C', str(ruff)]
def clean():
    assert subprocess.check_output(git + ['rev-parse', 'HEAD']).decode().strip() == pinned
    assert not subprocess.check_output(git + ['status', '--porcelain'])
clean()
store = [pool/'target', pool/'shared']
env = dict(os.environ, RUSTUP_HOME=str(pool/'rustup'), RUSTUP_AUTO_INSTALL='0',
           CARGO_HOME=str(pool/'registry-home'), CARGO_TARGET_DIR=str(store[0]),
           CARGO_BUILD_BUILD_DIR=str(store[1]), CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',
           CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all', CARGO_TERM_COLOR='never', LC_ALL='C.UTF-8')
for key in ['CARGO_BUILD_JOBS', 'CARGO_ENCODED_RUSTFLAGS', 'RUSTFLAGS', 'RUSTC_WRAPPER', 'OHM_FRONTEND_SCHEDULING_SCREEN']:
    env.pop(key, None)
cargo = ['cargo', '+ohm', 'check', '--locked', '--offline']
workloads = dict(parser=('parser-ast', []), lint=('linter', []), scoped=('parser-ast', ['-p', 'ruff_python_parser']))
if a.phase == 'guard':
    workloads = {'scoped': workloads['scoped']}
rng = random.Random(a.seed)
plan = []
for block in range(a.blocks):
    for workload in rng.sample(list(workloads), len(workloads)):
        if a.phase == 'screen':
            arms = rng.sample(['default', 'double', 'single'], 3)
        else:
            arms = ('parent', 'candidate', 'candidate', 'parent') if rng.randrange(2) else ('candidate', 'parent', 'parent', 'candidate')
        plan += [(block, workload, arm) for arm in arms]
def write(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
real = pool/'rustup/toolchains/ohm/bin/cargo'
write(a.out/'plan.json', dict(host=socket.gethostname(), affinity=sorted(os.sched_getaffinity(0)),
      ruff=pinned, seed=a.seed, phase=a.phase, plan=plan,
      drivers={p.name:sha(p) for p in sorted((pool/'frozen-toolchain/lib').glob('librustc_driver*.so'))},
      programs={k:sha(p) for k,p in ([('probe', real)] if a.phase=='screen' else [('parent',a.parent),('candidate',a.candidate)])}))
def choose(arm):
    if a.phase == 'screen':
        env['OHM_FRONTEND_SCHEDULING_SCREEN'] = arm
    else:
        subject = {'parent':a.parent, 'candidate':a.candidate}[arm]
        if not os.path.samefile(real, subject):
            tmp = real.with_name('cargo.subject')
            os.link(subject, tmp)
            tmp.replace(real)
def grouped(paths):
    total = hashlib.sha256()
    for path in sorted(set(paths)):
        assert any(path.is_relative_to(s) for s in store),path
        total.update(str(path.relative_to(pool)).encode() + b'\0')
        total.update(bytes.fromhex(sha(path)))
    return total.hexdigest()
def run(directory, flags, *, message, artifacts):
    directory.mkdir()
    with (directory/'stdout').open('wb') as stdout, (directory/'stderr').open('wb') as stderr:
        start_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        start_ns = time.monotonic_ns()
        subprocess.run(cargo + flags + (['--message-format=json'] if message else []) + (['--timings'] if a.timings else []), cwd=ruff, env=env, stdout=stdout, stderr=stderr, check=True)
        wall_ns = time.monotonic_ns() - start_ns
        end_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    log = (directory/'stderr').read_text()
    assert 'Blocking waiting' not in log, (directory, log)
    row = dict(wall_ns=wall_ns, user_s=end_usage.ru_utime-start_usage.ru_utime, sys_s=end_usage.ru_stime-start_usage.ru_stime,
               compile_lines=sorted(s.strip() for s in log.splitlines() if s.strip().startswith(('Checking ', 'Compiling '))))
    if message:
        data = [x for x in map(json.loads, (directory/'stdout').read_bytes().splitlines()) if x['reason']=='compiler-artifact']
        units = [(j['package_id'], j['target']['name'], j['target']['kind'], j['profile']['test']) for j in data]
        row.update(units=len(units), roster=hashlib.sha256(json.dumps(sorted(units)).encode()).hexdigest(),
                   dirty=sorted(u for u,j in zip(units, data) if not j['fresh']))
        if artifacts:
            metas = {Path(f) for j in data for f in j['filenames'] if f.endswith('.rmeta')}
            apis = {f for s in store for f in s.rglob('*.public-api-hash')}
            assert metas and apis,(len(metas),len(apis))
            row.update(metas=len(metas),apis=len(apis),meta_digest=grouped(metas),api_digest=grouped(apis))
            if a.timings:
                row['rmeta_sizes'] = {j['target']['name']: sum(Path(f).stat().st_size for f in j['filenames'] if f.endswith('.rmeta')) for j in data if not j['fresh']}
    if a.timings:
        report, = store[0].rglob('cargo-timing.html')
        raw = report.read_text().split('const UNIT_DATA = ', 1)[1]
        units, _ = json.JSONDecoder().raw_decode(raw)
        write(directory/'timings.json', units)
    write(directory/'receipt.json', row)
    return row
def restore(label):
    for s in store:
        subprocess.run(['rsync','-a','--delete','--checksum',str(pool/('checkpoint-'+label)/s.name)+'/',str(s)+'/'],check=True)
@contextlib.contextmanager
def edit(label):
    patch=pool/'entropy-corpus'/(label+'.patch')
    subprocess.run(git+['apply','--reverse','--whitespace=nowarn',str(patch)],check=True)
    try:
        yield
    finally:
        subprocess.run(git+['apply','--whitespace=nowarn',str(patch)],check=True)
        clean()
control='default' if a.phase=='screen' else 'parent'
select= 'discovery' if a.phase in ('screen', 'guard') else 'holdout'
saved=real.with_name('cargo.before-'+a.out.name)
os.link(real,saved)
try:
    choose(control)
    for name in dict.fromkeys('scoped' if flags else 'workspace' for _,flags in workloads.values()):
        stamp=pool/('checkpoint-'+name)
        flags=workloads['scoped'][1] if name=='scoped' else []
        if not stamp.exists():
            run(a.out/('warm-'+name),flags,message=True,artifacts=False)
            primed=run(a.out/('fresh-'+name),flags,message=True,artifacts=False)
            assert not primed['dirty']
            stamp.mkdir()
            for s in store:
                subprocess.run(['cp','-a',s,stamp/s.name],check=True)
        if name=='workspace':
            restore(name)
    expected={}
    for i,(block, key, arm) in enumerate(plan):
        label,flags=workloads[key]; fixture=label+'-'+select
        choose(arm)
        restore('scoped' if flags else 'workspace')
        tag=f'{i:03}-{key}-{arm}'
        with edit(fixture):
            if a.phase == 'screen':
                result=run(a.out/tag,flags,message=True,artifacts=True)
                assert result['dirty']
            else:
                result=run(a.out/tag,flags,message=False,artifacts=False)
                check=run(a.out/(tag+'-verify'),flags,message=True,artifacts=True)
                assert not check['dirty'] and result['compile_lines']
                result.update({k:v for k,v in check.items() if k in ('roster','units','meta_digest','api_digest','metas','apis')})
            sig={k:v for k,v in result.items() if k in ('dirty','roster','units','meta_digest','api_digest','metas','apis','compile_lines')}
            assert sig == expected.setdefault(key,sig),(tag,{k for k in sig if sig[k]!=expected[key][k]})
            row=dict(block=block, index=i, workload=key, arm=arm, **result)
            with (a.out/'samples.jsonl').open('a') as stream:
                stream.write(json.dumps(row)+'\n')
            print(tag,'wall',round(row['wall_ns']/1e9,3),'CPU',round(row['user_s']+row['sys_s'],3),'artifacts',row['units'],'rebuilt',len(row['compile_lines']),flush=True)
finally:
    saved.replace(real)
    clean()
