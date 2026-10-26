"""Pick discovery and holdout edits before collecting performance data."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASE = '93526150df078af7dd8fc4226cdcc469539d2001'
SEED = 'ohm-ruff-entropy-20261026-stage2'
STRATA = ('linter', 'parser-ast', 'formatter', 'shared-library', 'cli-workspace', 'test-target')
previous = {BASE, 'da8ee78491f784cdead4c69e83c58bc87fd0622c', '47eb6ee42b046338b91a9c0131b6283a348ff12d'}
repo, out = map(Path, sys.argv[1:3])

def git(*args, **kwargs):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, **kwargs)

def category(paths):
    rust = [p for p in paths if p.endswith('.rs')]
    if not rust or any(not p.startswith('crates/') for p in rust): return
    packages = {p.split('/')[1] for p in rust}
    if len(packages) != 1: return
    package, = packages
    if not package.startswith('ruff'): return
    if all('/tests/' in p for p in rust): return 'test-target'
    if package == 'ruff_linter': return 'linter'
    if package in ('ruff_python_ast', 'ruff_python_parser'): return 'parser-ast'
    if package in ('ruff_python_formatter', 'ruff_formatter'): return 'formatter'
    if package in ('ruff', 'ruff_workspace', 'ruff_server'): return 'cli-workspace'
    if package in ('ruff_db', 'ruff_cache', 'ruff_diagnostics', 'ruff_source_file', 'ruff_python_trivia', 'ruff_text_size', 'ruff_python_semantic', 'ruff_python_stdlib', 'ruff_python_literal'): return 'shared-library'

def patch(sha):
    return git('diff', '--no-ext-diff', '--no-renames', '--binary', sha+'^', sha, check=True).stdout

log = git('log', '--first-parent', '--no-merges', '--max-count=8500', '--no-renames', '--format=@@%H %s', '--numstat', BASE, check=True).stdout.decode()
candidates = {s:[] for s in STRATA}
for index, block in enumerate(log.split('@@')[1:]):
    header, *stats = block.splitlines()
    sha, title = header.split(' ', 1)
    if sha in previous: continue
    rows = [line.split('\t', 2) for line in stats if line.strip()]
    if not rows or len(rows)>18 or any(len(r)!=3 or not r[0].isdigit() for r in rows): continue
    paths = [r[2] for r in rows]
    if any(p.endswith(('.lock','.toml')) or p.startswith(('.github/','scripts/','vendor/')) for p in paths): continue
    lines = sum(int(a)+int(d) for a,d,f in rows if f.endswith('.rs'))
    if not 2<=lines<=170: continue
    kind = category(paths)
    if kind and (index<1600 or kind=='test-target'):
        rank=hashlib.sha256((SEED+' '+sha).encode()).hexdigest()
        candidates[kind].append((rank, sha, title, paths, lines))

manifest = []
out.mkdir(exist_ok=True,parents=True)
for kind in STRATA:
    selected = []
    for rank,sha,title,paths,lines in sorted(candidates[kind]):
        raw = patch(sha)
        if len(raw)>140000: continue
        if git('apply','--reverse','--check','--whitespace=nowarn','-',input=raw).returncode: continue
        slot = ('discovery','holdout')[len(selected)]
        name = kind+'-'+slot
        item=dict(label=name, stratum=kind, split=slot, commit=sha, title=title, rust_delta_lines=lines,
                  paths=paths, patch_sha256=hashlib.sha256(raw).hexdigest(), rank=rank)
        (out/(name+'.patch')).write_bytes(raw)
        selected.append(item)
        print(name,sha[:10],lines,title,flush=True)
        if len(selected)==2: break
    manifest.extend(selected)
    assert len(selected)==2 or (kind=='test-target' and len(selected)==1),(kind,len(candidates[kind]),len(selected))
(out/'manifest.json').write_text(json.dumps(dict(ruff=BASE,seed=SEED,direction='reverse',candidates={k:len(v) for k,v in candidates.items()},fixtures=manifest),indent=2)+'\n')
