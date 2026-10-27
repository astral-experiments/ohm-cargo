"""Project edited native invocations onto whole Ruff products and their previous ELF payloads."""
from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import sys

parser = argparse.ArgumentParser(description=__doc__)
for name in ('runner', 'results', 'destination'):
    parser.add_argument(name, type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.runner))
from processes import records
from products import inputs_elf_key

def read(path):
    return json.loads(path.read_bytes())

def write(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True, separators=(',', ':')) + '\n')

def sha(path):
    with path.open('rb') as fp:
        return hashlib.file_digest(fp, 'sha256').hexdigest()

def product_roster(directory, expected):
    selected = {}
    for buf in (directory/'stdout').read_bytes().splitlines():
        row = json.loads(buf)
        if row.get('reason') != 'compiler-artifact' or not row['package_id'].startswith('path+'):
            continue
        for name in row['filenames']:
            key = inputs_elf_key(name)
            if key not in expected: continue
            obj = {'package': row['package_id'].rsplit('#',1)[0].rsplit('/',1)[-1],
                   'target': row['target']['name'], 'kind': row['target']['kind'], 'test': row['profile']['test']}
            assert key not in selected or selected[key] == obj
            selected[key] = obj
    assert set(selected) == set(expected), (selected.keys() ^ expected.keys())
    return selected

def delta(d, old, new, report):
    roster=product_roster(d,new['product']['elf'])
    by_proc={(j['pid'],j['crate']):j for j in new['processes']['jobs']}
    jobs=[]; links=[]
    for pid,path,argv in records(d):
        image=Path(path)
        if image.name=='rustc' and '--crate-name' in argv:
            crate=argv[argv.index('--crate-name')+1]
            j=by_proc.get((pid,crate))
            if j is None: continue
            kind='link-only' if any(a in ('link-only','-Zlink-only') for a in argv) else 'full'
            assert j['kind']==kind
            externs=sorted({argv[i+1].split('=',1)[0] for i,v in enumerate(argv) if v=='--extern'})
            jobs.append({'process':pid,'crate':crate,'kind':kind,'parser_direct': 'ruff_python_parser' in externs,
                         'test_harness':'--test' in argv,'extern_crates':externs,'trace_sha256':sha(d/pid)})
        if image.name!='ld.bfd' or image.parent.name!='wild-ld':continue
        assert pid in new['processes']['native']['wild'] and '-o' in argv
        out='/'.join(Path(argv[argv.index('-o')+1]).parts[-4:])
        package,unit,folder,basename=out.split('/')
        assert len(unit)==16 and folder=='out',(out,report)
        choices=[key for key,r in roster.items() if key==out or
                 (r['package']==package and not r['test'] and Path(key).parent.as_posix()=='debug' and Path(key).name==basename)]
        assert len(choices)==1,(out,choices,list(roster),report)
        key,=choices;left,right=old['product']['elf'][key],new['product']['elf'][key]
        changed={};l,r=left['section_hashes'],right['section_hashes']
        for n in sorted(l.keys()|r.keys()):
            if l.get(n)==r.get(n):continue
            if n not in l or n not in r: changed[n]=['presence'];continue
            changed[n]=sorted(f for f in l[n].keys()|r[n].keys() if l[n].get(f)!=r[n].get(f))
        links.append({'process':pid,'trace_sha256':sha(d/pid),'wild_output':out,'product':key,
                      **roster[key], 'raw':[left['raw'],right['raw']],
                      'masked':[left['content_with_two_wild_fields_masked'],right['content_with_two_wild_fields_masked']],
                      'section_fields_changed':changed,
                      'text_bytes':[l['.text']['bytes'],r['.text']['bytes']],
                      'rodata_bytes':[l['.rodata']['bytes'],r['.rodata']['bytes']]})
    assert Counter((j['process'],j['crate']) for j in jobs)==Counter((j['pid'],j['crate']) for j in new['processes']['jobs'])
    assert len({w['product'] for w in links})==len(links)==new['native_totals']['wild']
    return {'jobs':jobs,'links':links,'previous_source':old['source_view'],'source':new['source_view'],
            'previous_receipt_sha256':sha(report[0]),'current_receipt_sha256':sha(report[1])}

p=read(args.runner/'novel-plan.json')
data={}
for mode in ('build','test'):
    data[mode]={}
    for arm in 'BC':
        previous='original-baseline'
        ds=args.results/'receipts'/mode/arm
        data[mode][arm]={}
        for edit in p['schedule']:
            for direction in ('edit','restore'):
                name=edit+'-'+direction
                aa,bb=[ds/key/'receipt.json' for key in (previous,name)]
                data[mode][arm][name]=delta(ds/name,read(aa),read(bb),(aa,bb))
                previous=name
write(args.destination,data)
