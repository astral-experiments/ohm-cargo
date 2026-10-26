"""Measure a held-out Ruff server edit in balanced three-arm blocks."""
import argparse
from contextlib import contextmanager
import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('phase', choices=['prepare', 'guard', 'measure'])
for name in ['pool', 'results', 'ruff', 'patch', 'toolchain', 'registry', 'parent']:
    parser.add_argument('--' + name, type=Path, required=True)
for name in ['seven', 'combined']:
    parser.add_argument('--' + name, type=Path)
parser.add_argument('--cpu', default='4-7')
parser.add_argument('--seed', default=946137, type=int)
a = parser.parse_args()
q, out, ruff = a.pool.resolve(), a.results.resolve(), a.ruff.resolve()
arms = ['parent', 'seven', 'combined']
real = q / 'runtime/bin/cargo'
tool = q / 'rustup/toolchains/ohm'
store = [q / 'target', q / 'shared']
command = ['taskset', '-c', a.cpu, 'cargo', '+ohm', 'check', '--locked', '--offline']
env = dict(os.environ, RUSTUP_HOME=str(q/'rustup'), RUSTUP_AUTO_INSTALL='0',
           CARGO_HOME=str(q/'home'), CARGO_TARGET_DIR=str(store[0]), CARGO_BUILD_BUILD_DIR=str(store[1]),
           CARGO_BUILD_JOBS='6', CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',
           CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all', CARGO_TERM_COLOR='never',
           GIT_OPTIONAL_LOCKS='0', SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',
           SSL_CERT_DIR='/etc/ssl/certs', LC_ALL='C.UTF-8')
for key in ['RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'RUSTC_WRAPPER', 'OHM_COUNT_DIR']:
    env.pop(key, None)

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ruff, env=env, text=True).strip()

def clean():
    assert git('rev-parse', 'HEAD') == '93526150df078af7dd8fc4226cdcc469539d2001'
    assert not git('status', '--porcelain')

clean()
assert sha(a.patch) == 'a8039aa2f1ac63b37ecb3e0fdd33fe54b26ca8ee604303581c8446e74ed2cde1'
index_path = Path(git('rev-parse', '--path-format=absolute', '--git-path', 'index'))
index_sha = sha(index_path)

def choose(arm):
    src = q / 'subjects' / arm
    if not real.is_file() or not real.samefile(src):
        temp = real.with_name('cargo.next')
        os.link(src, temp)
        temp.replace(real)

def invoke(*, json_messages=False, counters=None):
    cmd = command + (['--message-format=json'] if json_messages else [])
    # Initialize the same Cargo collector in every invocation. Its loader affects
    # the registry namespace; only its child-tracing switch changes for scoring.
    with TemporaryDirectory(dir=q) as logs:
        run_env = dict(env, OHM_COUNT_DIR=str(counters or logs),
                       OHM_CG_CHILDREN='no' if counters is None else 'yes')
        proc = subprocess.run(cmd, cwd=ruff, env=run_env, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    assert 'Blocking waiting' not in proc.stderr, proc.stderr
    return proc

def verify():
    proc = invoke(json_messages=True)
    units = [j for j in map(json.loads, proc.stdout.splitlines()) if j['reason'] == 'compiler-artifact']
    assert len(units) == 520 and all(j['fresh'] for j in units)
    roster = sorted((j['package_id'], j['target']['name'], j['target']['kind'], j['profile']['test']) for j in units)
    metas = {Path(f) for j in units for f in j['filenames'] if f.endswith('.rmeta')}
    apis = {f for s in store for f in s.rglob('*.public-api-hash')}
    assert metas and apis
    return dict(roster=roster, metadata={str(f.relative_to(q)):sha(f) for f in sorted(metas)},
                api={str(f.relative_to(q)):sha(f) for f in sorted(apis)})

def restore():
    for s in store:
        subprocess.run(['rsync', '-a', '--delete', '--checksum', str(q/'checkpoint'/s.name)+'/', str(s)+'/'], check=True)

@contextmanager
def edit():
    git('apply', '--reverse', '--whitespace=nowarn', str(a.patch))
    try:
        assert sha(index_path) == index_sha
        yield
    finally:
        git('apply', '--whitespace=nowarn', str(a.patch))
        clean()
        assert sha(index_path) == index_sha

def one(arm, tag, count, reference):
    choose(arm)
    restore()
    with edit(), TemporaryDirectory(dir=q) as tmp:
        proc = invoke(counters=Path(tmp) if count else None)
        counts = []
        for f in Path(tmp).glob('count.*'):
            data = f.read_bytes()
            cmd = re.search(rb'^cmd:\s+(.+)$', data, re.M)[1].decode()
            ir = int(re.search(rb'^summary: (\d+)$', data, re.M)[1])
            counts.append((cmd,ir))
        groups = sorted((Path(cmd.split()[0]).name, re.search(r' --crate-name (\S+)',cmd)[1] if ' --crate-name ' in cmd else '') for cmd,ir in counts)
        if count:
            assert groups.count(('cargo','')) == 1 and any(s=='rustc' for s,_ in groups), groups
        records = verify()
        dirty = sorted(line.strip() for line in proc.stderr.splitlines() if line.strip().startswith(('Checking ','Compiling ')))
        assert dirty
        records['dirty_diagnostics'] = dirty
        if reference is None:
            save(out/'artifact-roster.json',records)
        elif records != reference:
            save(out/(tag+'-mismatch.json'),records)
            raise ValueError(f'{tag}: artifact parity failed')
        receipt = dict(arm=arm,groups=groups, counts=sorted(counts), total_ir=sum(i for cmd,i in counts), index_sha=index_sha)
        save(out/(tag+'.json'),receipt)
        return receipt,records

if a.phase == 'prepare':
    q.mkdir(mode=0o700)
    out.mkdir()
    for d in [*store, q/'home', q/'subjects', real.parent, tool/'bin']:
        d.mkdir(parents=True, exist_ok=True)
    (q/'home').chmod(0o700)
    shutil.copytree(a.registry/'registry',q/'home/registry',symlinks=True)
    (tool/'lib').symlink_to(a.toolchain/'lib',target_is_directory=True)
    for name in ['rustc','rustdoc']:
        (tool/'bin'/name).symlink_to(a.toolchain/'bin'/name)
    proxy=tool/'bin/cargo'
    proxy.write_text('#!/bin/sh\nexec valgrind --tool=callgrind --trace-children="$OHM_CG_CHILDREN" '
        '--cache-sim=no --branch-sim=no --log-file="$OHM_COUNT_DIR/log.%p" '
        '--callgrind-out-file="$OHM_COUNT_DIR/count.%p" ' + shlex.quote(str(real)) + ' "$@"\n')
    proxy.chmod(0o755)
    shutil.copy2(a.parent,q/'subjects/parent')
    choose('parent')
    invoke()
    save(out/'warm.json',verify())
    (q/'checkpoint').mkdir()
    for s in store:
        subprocess.run(['cp','-a',s,q/'checkpoint'/s.name],check=True)
    save(out/'setup.json',dict(index=index_sha,parent=sha(a.parent),patch=sha(a.patch),argv=command,search_path=env['PATH']))
else:
    selected=arms[:2] if a.phase=='guard' else arms
    assert all(getattr(a,k) for k in selected)
    assert sha(q/'subjects/parent')==sha(a.parent)
    setup=json.loads((out/'setup.json').read_text())
    assert setup['index']==index_sha and setup['search_path']==env['PATH']
    for arm in selected[1:]:
        shutil.copy2(getattr(a,arm),q/'subjects'/arm)
    schedule=list(itertools.permutations(arms))*2
    random.Random(a.seed).shuffle(schedule)
    save(out/(a.phase+'-plan.json'),dict(seed=a.seed,schedule=schedule,subjects={k:sha(q/'subjects'/k) for k in selected}))
    reference=None
    for arm in selected:
        choose(arm)
        restore()
        verify()
        _,reference=one(arm,a.phase+'-preflight-'+arm,False,reference)
    if a.phase=='guard':
        raise SystemExit(0)
    cache_dirs = [q/'home'/name for name in ['.ohm-registry-json-v1','.ohm-registry-json-v2','.ohm-git-index-sha1dc-v1']]
    def cache_inventory():
        return {str(f.relative_to(q/'home')):(f.stat().st_ino,f.stat().st_size,f.stat().st_mtime_ns,sha(f))
                for d in cache_dirs for f in d.iterdir()}
    assert all(d.is_dir() and any(d.iterdir()) for d in cache_dirs), 'the private caches must be active'
    for cycle in range(5):
        before=cache_inventory()
        for arm in arms:
            auxiliary,records=one(arm,f'settle-{cycle}-{arm}',False,reference)
        if before==cache_inventory():
            break
    else:
        raise RuntimeError('manifest and Git proof records did not settle')
    cache_before=cache_inventory()
    proc_roster=None
    with (out/'blocks.csv').open('x', newline='') as f:
        writer=csv.writer(f); writer.writerow(['block','position','arm','total_ir'])
        for block,order in enumerate(schedule):
            for pos,arm in enumerate(order):
                receipt,_=one(arm,f'{block:02}-{pos}-{arm}',True,reference)
                if proc_roster is None:
                    proc_roster=receipt['groups']
                assert receipt['groups']==proc_roster
                writer.writerow([block,pos,arm,receipt['total_ir']]); f.flush()
                print(block,pos,arm,receipt['total_ir'],flush=True)
    assert cache_before==cache_inventory()
    save(out/'cache-validation.json',dict(stable_record_counts={d.name:sum(1 for f in d.iterdir()) for d in cache_dirs},stable_git_index=index_sha))
