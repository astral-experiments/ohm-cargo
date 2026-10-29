"""Compile a real linter consumer against the exact just-declared unit and print its rule rows."""
from pathlib import Path
import os,subprocess as sp,json,hashlib
def cli(env,proxy,root,work,rep,expect,out):
    out.mkdir(mode=0o700)
    n=[json.loads(line)for line in (rep/'cargo.jsonl').read_text().splitlines()]
    libs={};dirs=set();native=set()
    for row in n:
        if row['reason']=='build-script-executed':
            native.update(row['linked_paths'])
        if row['reason']!='compiler-artifact':continue
        for f in map(Path,row['filenames']):
            if f.suffix in ('.rlib','.so','.rmeta'):dirs.add(f.parent)
            if f.suffix=='.rlib' and row['target']['name']in ('ruff_linter','ruff_python_ast'):
                name=row['target']['name']
                if name=='ruff_linter':
                    f=next(Path(v)for v in row['filenames']if v.endswith('.rmeta')).with_suffix('.rlib')
                assert name not in libs;libs[name]=f
    assert set(libs)=={'ruff_linter','ruff_python_ast'}
    prog=out/'lint-cli'
    argv=[proxy,'+ohm','--edition=2024','--crate-name','fstring_rule_consumer',root/'reader.rs','-o',prog]
    for k,p in sorted(libs.items()):argv+=['--extern',k+'='+str(p)]
    for p in sorted(dirs):argv+=['-L','dependency='+str(p)]
    for q in sorted(native):argv+=['-L',q]
    cmp=sp.run(argv,cwd=work,env=env,capture_output=True);(out/'compiler.stderr').write_bytes(cmp.stderr);assert cmp.returncode==0,cmp.stderr.decode()[-1400:]
    data=b'''print(f"{x}abc" or "bar")
print(f"" f"{x}" or "bar")
print(f"{'x':.0}" or "bar")
print(f"{x > y}" or "bar")
'''
    p=sp.run([prog],input=data,env=env,cwd=work,capture_output=True);assert p.returncode==0 and p.stdout==(''.join(f'{i} SIM222\n'for i in expect)).encode(),(p.returncode,p.stdout,p.stderr[-800:])
    sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
    res={'exit':p.returncode,'stdout':p.stdout.decode(),'stderr_sha256':hashlib.sha256(p.stderr).hexdigest(),'executable':sha(prog),'input':hashlib.sha256(data).hexdigest(),'linter':sha(libs['ruff_linter']),'ast':sha(libs['ruff_python_ast'])}
    (out/'result.json').write_text(json.dumps(res,sort_keys=True,indent=2)+'\n')
