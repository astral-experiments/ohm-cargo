"""Read the terminal H2 process traces and physical Ruff products without invoking Cargo."""
import ast
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import socket
import sys

r=Path('/dev/shm/ohm-text-size-first-selection-20261028');can=r/'logical'
sdk=Path('/dev/shm/ohm-published-member-h2-20261028/installed17')
wild=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
def h(x):return hashlib.sha256(x).hexdigest()
def sha(f):
    with f.open('rb') as d:return hashlib.file_digest(d,'sha256').hexdigest()
def read(f):return json.loads(f.read_bytes())
def safe(s):return re.sub(r'(/registry/(?:src|cache|index)/)[^/\s]+',r'\1REGISTRY',s)
def key(s):return h(s.encode())
def dig(x):return h(json.dumps(x,sort_keys=True,separators=(',',':')).encode())
assert socket.gethostname()=='charlie-ohm-relink-b-1024' and (r/'native.exit').read_text()=='0'
rx=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[0-9a-f]+|NULL).*?\)\s+= 0$')
out={'sdk':{'rustc':sha(sdk/'bin/rustc'),'wild':sha(wild)},'registration':read(r/'plan-registration.json'),'runs':{},
     'api':{arm:{name: (r/'receipts'/arm/name).read_text() for name in
         (('api-probe.rs','api-rustc.stderr','api-rustc.status.json') if arm=='before-build' else
          ('api-probe.rs','api-rustc.stderr','api-rustc.status.json','api-run.stdout','api-run.stderr','api-run.status.json'))}
            for arm in ('before-build','after-build')}}
for d in sorted((r/'receipts').iterdir()):
    meta=read(d/'products.json');exes={j['file'] for j in meta['harness'].values()};children=[]
    for f in sorted((d/'trace').glob('exec.*')):
        lines=f.read_bytes().splitlines()
        for line in lines:
            mat=rx.fullmatch(line)
            if not mat:
                assert not(line.startswith(b'execve(') and line.endswith(b'= 0')),f
                continue
            exe=Path(ast.literal_eval(mat[1].decode()));argv=ast.literal_eval(mat[2].decode())
            assert str(exe) not in exes
            actual=None
            if exe.name=='rustc' and exe.samefile(sdk/'bin/rustc') and '--crate-name' in argv:
                if argv[argv.index('--crate-name')+1] in ('__','___'):continue
                actual='rustc'
            elif exe.name in ('ld','ld.bfd','ld.lld','wild','wild-ld','rust-lld','mold') and '-o' in argv:
                assert exe.samefile(wild);actual='wild'
            if actual is None:continue
            end=re.fullmatch(rb'\+\+\+ exited with (\d+) \+\+\+',lines[-1]);assert end and int(end[1])==0
            children.append({'trace':f.name,'trace_sha256':sha(f),'original_exec':h(line),'original_argv':dig(argv),
                             'kind':actual,'binary':out['sdk'][actual],'argv':[safe(a) for a in argv],'exit':0})
    old=read(d/'jobs.json')
    assert collections.Counter(j['raw'] for j in old)==collections.Counter(j['original_exec'] for j in children)
    rows=[json.loads(l) for l in (d/'cargo.stdout').read_bytes().splitlines()]
    groups=sorted(dig({k:e[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')})
                  for e in rows if e['reason']=='compiler-artifact')
    assert len(set(groups))==len(groups)==meta['units'] and dig(groups)==meta['roster']
    item=dict(children=children,typed_cargo_rows=groups,source_sha256=sha(d/'cargo.stdout'),products_sha256=sha(d/'products.json'))
    if d.name[:1].isdigit():
        i,arm,stage=d.name.split('-');state=r/f'state-{i}-{arm}'
        current={}
        for path,expected in meta['elf'].items():
            logical=Path(path).relative_to(can);assert logical.parts[0] in ('target','shared')
            f=state/logical;assert sha(f)==expected
            current[key(path)]={'sha256':expected,'length':f.stat().st_size,'basename':f.name}
        item['terminal_elf']=current
    out['runs'][d.name]=item
blob=json.dumps(out,sort_keys=True,separators=(',',':')).encode()
sys.stdout.buffer.write(gzip.compress(blob,mtime=0))
