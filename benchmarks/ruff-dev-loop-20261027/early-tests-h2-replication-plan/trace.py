"""Read native process execs and exits without collecting child environments."""
from pathlib import Path
import ast,collections,json,re,hashlib
from products import digest,put
def load(f):return json.loads(f.read_bytes())
def canonical(v,worktree):
    p=Path(v);return str(p.relative_to(worktree)) if p.is_absolute() and p.is_relative_to(worktree) else v
def audit(out,worktree):
    done={};calls=[];traces={}
    for f in sorted((out/'trace').glob('exec.*')):
        pid=int(f.suffix[1:]);b=f.read_bytes();pending=None
        traces[str(pid)]=[hashlib.sha256(b).hexdigest(),len(b)]
        for row in b.splitlines():
            ts,_,line=row.partition(b' ');time=int(ts.split(b'.')[0])*10**9+int(ts.split(b'.')[1].ljust(9,b'0'))
            if fin:=re.match(rb'^\+\+\+ exited with (\d+) \+\+\+$',line):done[pid]=[time,int(fin[1])]
            if line.startswith((b'execve(',b'execveat(')) and line.endswith(b'<unfinished ...>'):
                assert pending is None;pending=(time,line.removesuffix(b'<unfinished ...>'));continue
            if m:=re.match(rb'^<\.\.\. (execve(?:at)?) resumed>(.*)$',line):
                assert pending;time,at=pending;line=at+m[2];pending=None
            if not line.startswith((b'execve(',b'execveat(')) or not re.search(rb'\)\s+= 0$',line):continue
            m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m,(pid,line[:110])
            image=ast.literal_eval(m[1].decode());args=ast.literal_eval(m[2].decode());assert isinstance(args,list) and all(isinstance(v,str) for v in args)
            calls.append(dict(pid=pid,start=time,image=image,argv=args,original_line=hashlib.sha256(row).hexdigest()))
        assert not pending
    product=load(out/'product.json')
    assert not set(product['executables']).intersection(z['image'] for z in calls)
    groups=collections.defaultdict(list);links=collections.defaultdict(list);native=collections.Counter()
    for rec in calls:
        pid=rec['pid'];args=rec['argv'];img=Path(rec['image']);name=img.name
        if name in ('gcc','cc','collect2','ld.bfd'):native[name]+=1
        if name=='rustc' and '--crate-name' in args and '--out-dir' in args and '--print=file-names' not in args:
            crate=args[args.index('--crate-name')+1]
            if crate in ('___','__'):continue
            key=digest([rec['image'],args])
            source=next((canonical(v,worktree) for v in args if v.endswith('.rs') and not v.startswith('-')),None)
            assert source or 'link-only' in args or '-Zlink-only' in args or (crate.startswith('autocfg_') and '-' in args)
            groups[key].append(dict(pid=pid,start=rec['start'],end=done.get(pid),source=source,test='--test' in args,crate=crate,
                kind='link' if ('link-only' in args or '-Zlink-only' in args) else 'full',signature=key,
                ty_extern=[a for a in args if a.startswith('ty_server=') and a.endswith('.rlib')]))
        if name=='ld.bfd' and 'wild-ld' in img.parts:
            assert '-o' in args and done.get(pid)[1]==0
            links[args[args.index('-o')+1]].append(dict(pid=pid,start=rec['start'],end=done[pid],
                argv=digest(args),ty_rlibs=[v for v in args if Path(v).name.startswith('libty_server-') and v.endswith('.rlib')]))
    witnesses=[v for group in groups.values() for v in group];assert all(z['end'] is not None for z in witnesses)
    bysrc=collections.defaultdict(list)
    for v in witnesses:
        if v['test'] and v['source'] and '/tests/' in v['source']:bysrc[v['source']].append(v)
    for vs in bysrc.values():vs.sort(key=lambda z:z['start'])
    result=dict(rustc=collections.Counter(v['kind'] for v in witnesses),total=len(witnesses),distinct=len(groups),
        repeated={k:g for k,g in groups.items() if len(g)>1},native=native,actual_wild=sum(map(len,links.values())),
        distinct_wild=len(links),target_link_groups=links,integration=bysrc,typed_compilers=witnesses,
        policy=[s.split('ohm_early_tests: ',1)[1] for s in (out/'stderr').read_text(errors='replace').splitlines() if 'ohm_early_tests: ' in s])
    put(out/'successful-executables.json',calls);put(out/'original-trace-index.json',traces);put(out/'physical.json',result)
    return result
