"""Bind all qualified native output vectors and compare typed Cargo products across image namespaces."""
from pathlib import Path,PurePosixPath
import gzip,hashlib,json,re,sys,tarfile
h=Path(__file__).resolve().parent;i=h.parent
root=h
sha=lambda b:hashlib.sha256(b).hexdigest()
inventory=json.loads(gzip.decompress((root/'inventory.json.gz').read_bytes()))
files={}
for tar in sorted(root.glob('*.tar.gz')):
    with tarfile.open(tar,mode='r|*') as t:
        for m in t:
            n=m.name
            if n.endswith(('/stdout','/product.json','/complete.json','/plan.json','/binding.json','/reader.stdout')) and '/trace/' not in n:
                b=t.extractfile(m).read();assert sha(b)==inventory[n][1];files[n]=b
J=lambda n:json.loads(files[n])
native=J('matched/complete.json');plan=J('matched/protocol/plan.json');contract={};raw={}
for arm,pkg,initial,stages in plan['histories']:
    name=arm+'-'+pkg;di=contract.setdefault(name,{})
    for (step,stage),pr in zip(stages,native[arm],strict=True):
        prefix='matched/'+name+'/'+step+'/'
        assert pr==J(prefix+'product.json') and pr['stage']==stage and pr['source']==plan['stub'][stage]==sha(files[prefix+'reader.stdout'])
        ref=di.setdefault(stage,dict(files=[],zips=[],zip_path=pr['zip_path'],diagnostics=pr['diagnostics'],statuses={}))
        refs=ref['files'];assert not refs or all(set(x)==set(pr['outputs']) for x in refs)
        if pr['outputs'] not in refs:refs.append(pr['outputs'])
        if pr['zip'] not in ref['zips']:ref['zips'].append(pr['zip'])
        assert pr['zip_path']==ref['zip_path'] and pr['diagnostics']==ref['diagnostics']
        ref['statuses'][step]=dict(dirty=sorted(pr['dirty']),jobs=pr['jobs'],wild=pr['wild'])
    if arm=='Cgold':continue
    for stage,ref in di.items():
        steps=ref['statuses']
        selected=['repeat-one','repeat-two'] if stage=='original' else ['edit-repeat-one','edit-repeat-two']
        if stage=='original' and 'restore-repeat-one' in steps:selected+=['restore-repeat-one','restore-repeat-two']
        before=steps[selected[0]]
        assert all(steps[n]==before for n in selected)
        assert before['jobs']==([['ty_vendored','full'],['ty_wasm','full']] if arm=='Bwasm' else ([['ty_vendored','full']] if arm=='Bproject' else [])),(name,stage,before)
        assert before['wild']==(1 if arm=='Bwasm' else 0)
        ref['settled_dirty']=before['dirty']
        if pkg=='ty_wasm':ref['edited_dirty']=steps['edit' if stage=='reversed' else 'restore']['dirty']
target=PurePosixPath('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027/member-build-matched-canonical-v1/ruff target')
def product(pth,anchor):
    p=PurePosixPath(pth);assert str(p)==pth and '..' not in p.parts
    absolute=p.is_absolute()
    if absolute:p=p.relative_to(target)
    parts=p.parts
    if parts[:3]==('debug','build','workspaces'):
        assert len(parts)>5 and parts[3:5]==anchor
        p=PurePosixPath(*parts[:4],'@toolchain@',*parts[5:])
    return str(target/p if absolute else p)
def collect(name,step):
    prefix='matched/'+name+'/'+step+'/'
    p=J(prefix+'product.json');rows=[json.loads(v) for v in files[prefix+'stdout'].splitlines()]
    names=set()
    for r in rows:
        if r['reason']=='compiler-artifact':
            for s in r['filenames']:
                f=PurePosixPath(s).relative_to(target).parts
                if f[:3]==('debug','build','workspaces'):
                    assert re.fullmatch(r'[0-9a-f]{16}',f[3]) and re.fullmatch(r'v2-[0-9a-f]{16}',f[4]);names.add(f[3:5])
    anchor,=names
    normalized=[]
    for r in rows:
        if r['reason']!='compiler-artifact':continue
        x={k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')}
        x['filenames']=[product(s,anchor) for s in x['filenames']]
        if x['executable'] is not None:x['executable']=product(x['executable'],anchor)
        normalized.append(json.dumps(x,sort_keys=True))
    return dict(anchor=anchor,roster=sorted(normalized),diagnostics=p['diagnostics'],native={product(s,anchor):v for s,v in p['outputs'].items()},zip=p['zip'],stub=p['source'],caller=sha(files[prefix+'reader.stdout']))
comp={}
for label,left,right in [
    ('wasm-original',('Bwasm-ty_wasm','repeat-two'),('Cwasm-ty_wasm','repeat-two')),
    ('wasm-edited',('Bwasm-ty_wasm','edit-repeat-two'),('Cwasm-ty_wasm','edit-repeat-two')),
    ('wasm-clean-edited',('Cwasm-ty_wasm','edit-repeat-two'),('Cgold-ty_wasm','clean-edit-repeat')),
    ('wasm-restored',('Bwasm-ty_wasm','restore-repeat-two'),('Cwasm-ty_wasm','restore-repeat-two')),
    ('project-original',('Bproject-ty_project','repeat-two'),('Cproject-ty_project','repeat-two'))]:
    a=collect(*left);b=collect(*right)
    for field in ('roster','diagnostics','zip','stub','caller'):assert a[field]==b[field],(label,field)
    assert a['native'].keys()==b['native'].keys()
    different={name:[v,b['native'][name]] for name,v in a['native'].items() if v!=b['native'][name]}
    comp[label]=dict(arms=[left,right],anchors=[a['anchor'],b['anchor']],typed_roster=sha(json.dumps(a['roster']).encode()),outputs=len(a['native']),raw_equal=len(a['native'])-len(different),different=different,zip=a['zip'],caller=a['caller'])
for f,obj in [('native-contract.json',contract),('native-cross.json',comp)]:
    (h/f).write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
print({k:[v['raw_equal'],v['outputs']] for k,v in comp.items()})
