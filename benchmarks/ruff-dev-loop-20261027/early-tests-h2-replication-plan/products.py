"""All 619 Cargo rows and 110 native products, based on the independent H7 reference reader."""
from pathlib import Path
import collections,hashlib,json
def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(f):
    with Path(f).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def put(f,v):Path(f).write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def products(out,t,printed,cmd,select):
    rows=[json.loads(l) for l in (out/'stdout').read_bytes().splitlines()]
    assert rows[-1]=={'reason':'build-finished','success':True}
    arts=[r for r in rows if r['reason']=='compiler-artifact']; natives={}; exes=set(); own=[]
    assert len(arts)>600
    for r in arts:
        if not r['package_id'].startswith('path+'):continue
        if r['executable']:exes.add(r['executable'])
        for n in r['filenames']:
            f=printed(t,n)
            if r['target']['name']=='ty_server' and r['target']['kind']==['lib'] and n.endswith('.rlib'):
                own.append(dict(path=n,sha256=sha(f),features=r['features'],fresh=r['fresh']))
            if f.suffix not in ('','.so'):continue
            with f.open('rb') as read:magic=read.read(4)
            if magic==b'\x7fELF':natives[n]=sha(f)
    assert len(own)==1 and exes<=natives.keys()
    target=[r for r in arts if r['package_id'].startswith('path+') and Path(r['manifest_path']).parent.name=='ty_server' and r['target']['name']=='e2e' and r['target']['kind']==['test']]
    rec=dict(units=len(arts),dirty=[(r['target']['name'],r['target']['kind']) for r in arts if not r['fresh']],
             native=natives,executables=sorted(exes),ty_server=own[0],e2e=[x['executable'] for x in target],
             roster=digest(sorted(json.dumps({k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for r in arts)),
             diagnostics=sorted(json.dumps([r['package_id'],r['target']['name'],r['message']],sort_keys=True) for r in rows if r['reason']=='compiler-message'))
    if cmd==select:
        assert (len(arts),len(exes),len(natives),len(target))==(619,102,110,1)
        assert collections.Counter(bool(r['profile']['test']) for r in arts if r['executable'])=={True:84,False:18}
    else:assert not target
    put(out/'product.json',rec)
    return rec
