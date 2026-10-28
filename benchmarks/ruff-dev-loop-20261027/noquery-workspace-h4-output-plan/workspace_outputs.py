"""Match output directories for the two known compiler identities and authorize only eight decoded ELF images."""
from pathlib import Path
import hashlib,json
from elf_gate import permitted_linker_width
ROOT=Path(__file__).resolve().parent
RULES=json.loads((ROOT/'distinguished-products.json').read_bytes())
TARGET=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027/native-target')
MARK='@observed-compiler@'
def key(arm,value):
    p=Path(value);assert arm in RULES['namespaces'] and p.is_absolute() and str(p)==value
    assert p.is_relative_to(TARGET) and '..' not in p.parts and MARK not in value
    rel=p.relative_to(TARGET).parts
    if rel[:3]==('debug','build','workspaces'):
        assert len(rel)>=8 and rel[3:5]==(RULES['workspace'],'v2-'+RULES['namespaces'][arm])
        return '/'.join(('target',*rel[:4],MARK,*rel[5:]))
    return '/'.join(('target',*rel))
def units(arm,path):
    rows=[x for line in path.read_bytes().splitlines() if (x:=json.loads(line)).get('reason')=='compiler-artifact']
    assert len(rows)==619
    out=[]
    for r in rows:
        unit={n:r[n] for n in ('package_id','manifest_path','target','profile','features','filenames','executable')}
        unit['filenames']=[key(arm,n) for n in unit['filenames']]
        if unit['executable'] is not None:unit['executable']=key(arm,unit['executable'])
        out.append(json.dumps(unit,sort_keys=True))
    return sorted(out)
def products(arm,data):
    out={key(arm,n):v for n,v in data.items()};assert len(out)==len(data)==110;return out
def admitted(arm,path,left,right):
    if left==right:return 'raw'
    if permitted_linker_width(left,right):return 'registered_wild_worker_field'
    assert arm in ('B','C') and path in RULES['known_products'],(arm,path,left,right)
    w=RULES['known_products'][path]
    for actual,old in ((left,w['older_reference']),(right,w['new_reference'])):
        assert actual==old or permitted_linker_width(actual,old),(path,actual,old)
    return 'exact_independently_decoded_product'
def compare(reference,root):
    allphases={};receipts={}
    for phase in ('cold','first','settled','settled2'):
        phase_units={arm:units(arm,root/('unscored-'+arm)/phase/'stdout') for arm in 'OABC'}
        base=phase_units['O'];assert all(base==u for u in phase_units.values())
        dig=hashlib.sha256(json.dumps(base,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        ex={a:sorted(key(a,n) for n in reference[a]['phases'][phase]['public_executables']) for a in 'OABC'}
        assert len(ex['O'])==102 and all(v==ex['O'] for v in ex.values());allphases[phase]={'matched_all_619_rows':dig,'executable_destinations':len(ex['O'])}
        if phase not in ('cold','first'):continue
        rows={a:products(a,json.loads((root/('unscored-'+a)/phase/'elf.json').read_bytes())) for a in 'OABC'}
        baseline=rows['O'];assert all(r.keys()==baseline.keys() for r in rows.values())
        receipts[phase]={arm:{name:admitted(arm,name,baseline[name],rows[arm][name]) for name in sorted(baseline)} for arm in 'ABC'}
        for arm,qual in receipts[phase].items():
            debug={n for n,reason in qual.items() if reason=='exact_independently_decoded_product'}
            assert debug==(set(RULES['known_products']) if arm in ('B','C') else set()),(arm,debug)
    return {'phase_rows':allphases,'cross_arm_ELF':receipts}
