"""Reconstruct every physical compiler, linker and artifact roster from the exported raw records."""
from pathlib import Path
import ast,collections,gzip,hashlib,json,re,subprocess,sys,tarfile

p=Path(__file__).resolve().parent;sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda b:json.loads(b)
if (p/'SHA256SUMS').exists():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=p,check=True)
index=read(gzip.decompress((p/'inventory.json.gz').read_bytes()));alls=read(gzip.decompress((p/'calls.json.gz').read_bytes()))
stock=len(alls)==25;assert stock or len(alls)==30
seen=set();data={};proc={};counts=collections.Counter()
argpat=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)')
def parse(key,name,b,aliased):
    group=proc.setdefault(key,{'calls':{},'jobs':{},'wild':{}});pending=None;images=[]
    for line in b.splitlines():
        if line.startswith((b'execve(',b'execveat(')) and line.endswith(b'<unfinished ...>'):
            assert pending is None;pending=line.removesuffix(b'<unfinished ...>');continue
        if m:=re.match(rb'^<\.\.\. (?:execve|execveat) resumed>(.*)$',line):
            assert pending is not None;line=pending+m[1];pending=None
        if not re.search(rb'\)\s+= 0$',line) or not line.startswith((b'execve(',b'execveat(')):continue
        m=argpat.match(line);assert m
        path=ast.literal_eval(m[1].decode());argv=ast.literal_eval(m[2].decode());images.append(path)
        if Path(path).name=='rustc' and '--out-dir' in argv and '--crate-name' in argv and '--print=file-names' not in argv:
            crate=argv[argv.index('--crate-name')+1]
            if crate in ('___','__'):continue
            kind='link-only' if '-Zlink-only' in argv or 'link-only' in argv else 'full'
            job=dict(crate=crate,kind=kind,source=next((x for x in argv if x.endswith('.rs') and not x.startswith('-')),None),
                     binary_dep=any('binary-dep-depinfo' in x for x in argv),argv=sha(m[2]))
            assert name not in group['jobs'];group['jobs'][name]=(job,aliased)
        if Path(path).name=='ld.bfd' and 'wild-ld' in Path(path).parts:
            assert name not in group['wild'];group['wild'][name]=(dict(path=argv[argv.index('-o')+1],argv=sha(m[2])),aliased)
    assert pending is None;group['calls'][name]=images
for tar in sorted(p.glob('*.tar.gz')):
    with tarfile.open(tar,mode='r|*') as t:
        for ent in t:
            name=ent.name;assert ent.isfile() and name in index and name not in seen
            f=t.extractfile(ent).read();original,portable,norig,nport,c=index[name]
            assert len(f)==nport and sha(f)==portable and (c or (original==portable and norig==nport));seen.add(name)
            if '/trace/exec.' in name:
                key,pid=name.rsplit('/trace/',1);parse(key,pid,f,bool(c))
            else:data[name]=f
assert seen==index.keys()
def J(k):return read(data[k])
out={}
for key,stored in sorted(alls.items()):
    row=J(key+'/physical.json');group=proc[key]
    images=[image for pid in sorted(group['calls']) for image in group['calls'][pid]]
    assert images==row['images'] and collections.Counter(Path(v).name for v in images)==row['all_names']
    for kind in ('jobs','wild'):
        reported=row[kind];assert {x['trace'] for x in reported}==group[kind].keys()
        for x in reported:
            raw,aliased=group[kind][x['trace']]
            assert all(x[field]==value for field,value in raw.items() if field!='argv' or not aliased)
    args=[(x['crate'],x['kind']) for x in row['jobs']]
    assert args==[tuple(x) for x in stored['jobs']] and len(row['wild'])==stored['wild']
    cmd=J(key+'/command.json');assert cmd.get('code',cmd.get('status'))==0
    assert cmd.get('argv',cmd.get('cmd'))==['cargo','+ohm','build','--locked','--offline','-j4','--message-format=json']
    assert cmd['stdout']==stored['stdout']==index[key+'/stdout'][0] and cmd['stderr']==index[key+'/stderr'][0]
    stream=[read(x) for x in data[key+'/stdout'].splitlines()];assert stream[-1]=={'reason':'build-finished','success':True}
    arts=[x for x in stream if x['reason']=='compiler-artifact'];assert all(not x['profile']['test'] for x in arts)
    pkg='ty_wasm' if 'ty_wasm' in key else 'ty_project';assert len(arts)==(304 if pkg=='ty_wasm' else 275)
    if not stored['products']:
        assert key=='v1/ty_project-unspaced/call-0';continue
    pr=J(key+'/product.json');assert [tuple(x) for x in pr['jobs']]==args and pr['wild']==len(row['wild']) and pr['units']==len(arts)
    dirty=[x['target']['name'] for x in arts if not x['fresh']];assert dirty==pr['dirty']
    diags=sorted(json.dumps(x,sort_keys=True) for x in stream if x['reason']=='compiler-message')
    assert pr['diagnostics']==diags
    d=pr.get('products',pr.get('outputs'));assert len(d)>=3 and all(len(x)==64 for x in d.values())
    assert pkg!='ty_wasm' or 'debug/libty_wasm.so' in d
    label,series,step=key.split('/');rec=dict(units=len(arts),dirty=dirty,jobs=args,wild=len(row['wild']),files=d)
    if stock:
        assert any(v['real_stub']=='721696b22e172c4f9dbe15ec5e04a04a9939188eca12d8110ab62f9de81d96a1' and v['entries']>400 for v in pr['zips'].values())
    else:
        plan=J('matched/protocol/plan.json');b=data[key+'/reader.stdout'];assert not data[key+'/reader.stderr']
        assert sha(b)==pr['source']==pr['caller']['sha256']==plan['stub'][pr['stage']] and len(b)==pr['caller']['bytes']
        assert b==data['matched/protocol/stub-'+pr['stage']+'.pyi'];rec['source']=pr['stage'];rec['zip']=pr['zip'];rec['caller']=sha(b)
    out.setdefault(label+'/'+series,{})[step]=rec
if stock:
    assert data['v1/protocol/exit']==b'1' and b'That compression method is not supported' in data['v1/failure.txt']
    assert data['v2/protocol/exit']==b'0' and not data['v2/protocol/stderr']
    assert sum(k.startswith('v1/') for k in alls)==9 and sum(k.startswith('v2/') for k in alls)==16
    rows=J('v2/complete.json')
    for series,v in rows.items():
        assert len(v)==4
        for j,item in enumerate(v):assert item==J('v2/'+series+'/call-'+str(j)+'/product.json')
else:
    assert data['matched/protocol/exit']==b'0' and not data['matched/protocol/stderr']
    plan=J('matched/protocol/plan.json')
    for a,pkg,initial,stages in plan['histories']:
        items=J('matched/complete.json')[a]
        for (step,kind),v in zip(stages,items,strict=True):
            assert v==J('matched/'+a+'-'+pkg+'/'+step+'/product.json') and v['stage']==kind
    for arm in ('Bwasm','Cwasm'):
        aa=out['matched/'+arm+'-ty_wasm'];gg=out['matched/Cgold-ty_wasm']
        for tag in ('edit','edit-repeat-one','edit-repeat-two'):
            assert aa[tag]['caller']==gg['clean-edit']['caller']
        assert aa['restore']['caller']==aa['cold']['caller']!=aa['edit']['caller']
result={k:{step:[v['units'],len(v['dirty']),dict(collections.Counter(kind for _,kind in v['jobs'])),v['wild']] for step,v in sorted(block.items())} for k,block in out.items()}
print(json.dumps(dict(commands=len(alls),typed_product_calls=sum(map(len,out.values())),trace_and_evidence_files=len(index),native=result),sort_keys=True))
