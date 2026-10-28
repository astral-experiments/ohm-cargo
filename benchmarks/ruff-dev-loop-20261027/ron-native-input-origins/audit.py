"""Reproduce source attribution from pinned public Cargo archives and exported native commitments."""
from pathlib import Path, PurePosixPath
import argparse, collections, hashlib, json, os, posixpath, re, subprocess, tarfile, tempfile, tomllib

HERE=Path(__file__).resolve().parent
RUFF='93526150df078af7dd8fc4226cdcc469539d2001'
RUST='337a07a79cf8f2b9466cf8593344e5a9c479a927'
def h(a):return hashlib.sha256(a).hexdigest()
def git(p,rev,f):return subprocess.check_output(['git','-C',p,'show',rev+':'+f])
def audit(args):
    reg=tomllib.loads(git(args.ruff,RUFF,'Cargo.lock').decode())['package']
    lock={(p['name'],p['version']):p for p in reg};binary=Path(args.blake3)
    ids={'ron':'0.12.0','serde_derive':'1.0.229','syn':'3.0.5','quote':'1.0.47','proc-macro2':'1.0.107','unicode-ident':'1.0.24'}
    macro=('serde_derive','syn','quote','proc-macro2','unicode-ident')
    def one_dep(name):
        if ' ' in name:return name.split(' ')[0],name.split(' ')[1]
        c=[k for k in lock if k[0]==name];assert len(c)==1,c;return c[0]
    todo=[('serde_derive',ids['serde_derive'])];seen=set()
    while todo:
        k=todo.pop()
        if k not in seen:seen.add(k);todo.extend(map(one_dep,lock[k].get('dependencies',[])))
    assert seen=={(n,ids[n]) for n in macro}
    code={};archives={}
    for n,v in ids.items():
        prefix=n+'-'+v;path=next(Path(args.registry_cache).glob('*/'+prefix+'.crate'))
        dig=h(path.read_bytes());assert dig==lock[(n,v)]['checksum']
        with tarfile.open(path) as t:
            mem={p.name.removeprefix(prefix+'/'):t.extractfile(p).read() for p in t.getmembers() if p.isfile()}
        chosen={k:val for k,val in mem.items() if k.endswith('.rs') and (k.startswith('src/') or k=='build.rs')}
        assert chosen and all(not re.search(rb'(?<![\w])(?:track_path|tracked_path|tracked)(?![\w])|\binclude!\s*\(',code) for code in chosen.values()),n
        for k,val in chosen.items():
            for ct in re.findall(rb'#\[path\s*=\s*"([^"]+)"',val):
                assert not ct.startswith(b'/') and b'..' not in ct.split(b'/'),(n,k,ct)
        archives[prefix]={'checksum_sha256':dig,'library_and_build_rust_sources_scanned':len(chosen),'source_list':sorted(chosen),'lock_dependencies':lock[(n,v)].get('dependencies',[])}
        if n=='ron':code=mem
    typed=json.loads((HERE/'inputs.json').read_bytes());lookup=json.loads((HERE/'make-role-paths.json').read_bytes())
    paths={r[1]:r for r in typed};assert len(paths)==45
    origin=lookup['C/cold/ron.d']['first_rule_real_path_sha256'];full=lookup['C/cold/nested.d']['first_rule_real_path_sha256']
    assert set(paths)==set(full);assert set(origin)=={r[1] for r in typed if r[0].startswith('registry-source/')}
    out=[]
    with tempfile.TemporaryDirectory() as tmp:
        for scope,identity,algo,digest,size in typed:
            if scope.startswith('registry-source/'):
                name=scope.split('/',2)[2];src=code[posixpath.normpath(name)]
                f=Path(tmp)/'raw';f.write_bytes(src)
                assert size==len(src) and algo=='blake3' and subprocess.check_output([binary,f],text=True).strip()==digest,(scope,size)
                matches=[]
                if name=='src/lib.rs':
                    parent='crate root';line=None
                elif name=='src/../README.md':
                    parent='src/lib.rs';matches=[i+1 for i,l in enumerate(code[parent].splitlines()) if b'#[doc = include_str!("../README.md")]' in l or b'#![doc = include_str!("../README.md")]' in l];line,=matches
                else:
                    pp=PurePosixPath(name);stem=pp.stem if pp.stem!='mod' else pp.parent.name
                    directory=pp.parent if pp.stem!='mod' else pp.parent.parent
                    parent=str(directory/('lib.rs' if str(directory)=='src' else 'mod.rs'))
                    pattern=rb'^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+'+stem.encode()+rb'\s*;'
                    matches=[i+1 for i,l in enumerate(code[parent].splitlines()) if re.match(pattern,l)];line,=matches
                role='builtin include_str and SourceMap' if name.endswith('README.md') else 'local Rust SourceMap'
                item={'package_path':name,'declaration_source':parent,'line':line,'source_sha256':h(src)}
            else:
                assert (scope.startswith('sdk/') or scope.startswith('target/')) and scope.endswith(('.rmeta','.so'))
                role=('SDK metadata' if scope.startswith('sdk/') else 'used proc-macro library' if scope.endswith('.so') else 'dependency metadata')
                item={}
            out.append(dict(scope=scope,exact_path_sha256=identity,actual_blake3=digest,bytes=size,role=role,ordinary_first_make_prerequisite=identity in origin,**item))
    selectors={'compiler/rustc_interface/src/passes.rs':[(629,636),(668,698),(720,740)],'compiler/rustc_expand/src/proc_macro_server.rs':[(508,511),(802,816)],'compiler/rustc_builtin_macros/src/source_util.rs':[(277,284)],'compiler/rustc_span/src/source_map.rs':[(290,306)]}
    rust={}
    for n,scopes in selectors.items():
        data=git(args.rust,RUST,n);rust[n]={'complete_file_sha256':h(data),'line_groups':scopes}
    count=dict(collections.Counter(r['role'] for r in out));assert count=={'SDK metadata':19,'dependency metadata':6,'used proc-macro library':1,'local Rust SourceMap':18,'builtin include_str and SourceMap':1}
    return {'ruff':RUFF,'rust':RUST,'registry_sources':archives,'compiler_sources':rust,'input_roles':out,'role_counts':count,'inputs_exclusively_requiring_proc_macro_tracked_path':0,'gdb_observed_foreign_span_operation':{'sha256':'e5ce34a67c082debe227745f334ee6ef6f4603ea18616b6abe2e1e595e1d8bdc','join':3,'direct_track_path_entry_instrumented':False},'actual_make_records':lookup}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ruff',type=Path,required=True);p.add_argument('--rust',type=Path,required=True);p.add_argument('--registry-cache',type=Path,required=True);p.add_argument('--blake3',type=Path,required=True);x=p.parse_args();print(json.dumps(audit(x),indent=2,sort_keys=True))
