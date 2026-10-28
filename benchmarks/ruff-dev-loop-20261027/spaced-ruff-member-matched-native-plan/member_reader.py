"""Build a new Rust caller against the exact libraries produced by the preceding Cargo command."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess

def search_args(root, package):
    evidence=json.loads((root/'physical.json').read_bytes())
    job,=[e for e in evidence['jobs'] if e['crate']==package and e['kind']=='full']
    for line in (root/'trace'/job['trace']).read_bytes().splitlines():
        m=re.match(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL).*?\)\s+= 0$',line)
        if not m or not m[2]:continue
        args=ast.literal_eval(m[2].decode())
        if '--crate-name' not in args or args[args.index('--crate-name')+1]!=package:continue
        assert hashlib.sha256(m[2]).hexdigest()==job['argv']
        return [item for i,x in enumerate(args) if x=='-L' for item in ('-L',args[i+1])]
    raise AssertionError(('original rustc invocation missing',package))

def validate(package, out, run, target, products, search, source, expected):
    code=out/'reader.rs';code.write_bytes(source)
    external={}
    for name in (package,'ty_vendored'):
        item,=[n for n in products if Path(n).name.startswith('lib'+name) and n.endswith('.rlib')]
        external[name]=str(target/item)
    binary=out/'reader';cmd=['rustc','+ohm','--edition=2024',code,'--cfg','member_'+('wasm' if package=='ty_wasm' else 'project'),'-C','debuginfo=0','-o',binary]
    for name,path in external.items():cmd+=['--extern',name+'='+path]
    cmd+=search
    result=run(cmd,out)
    (out/'reader.compile.stderr').write_bytes(result.stderr);(out/'reader.compile.stdout').write_bytes(result.stdout)
    assert result.returncode==0,('independent caller compile',result.stderr[-3000:])
    invoke=run([binary],out)
    (out/'reader.stdout').write_bytes(invoke.stdout);(out/'reader.stderr').write_bytes(invoke.stderr)
    assert invoke.returncode==0 and not invoke.stderr and invoke.stdout==expected,('real embedded stub mismatch',invoke.returncode)
    return dict(sha256=hashlib.sha256(invoke.stdout).hexdigest(),bytes=len(invoke.stdout),externs=external,
                search_dirs=len(search)//2,binary=hashlib.sha256(binary.read_bytes()).hexdigest())
