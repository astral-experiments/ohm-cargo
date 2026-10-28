"""Export the six v4 command receipts and every independently examined changed test product."""
from pathlib import Path
import gzip,hashlib,json,re,runpy,shutil
p=Path(__file__).resolve().parent; ex=runpy.run_path(p/'export2.py'); D,O,h,save=ex['D'],ex['O'],ex['h'],ex['save']
out=D/'exports'/'raw-v4-first-occurrence';out.mkdir(exist_ok=False)
digest=lambda b:hashlib.sha256(b).hexdigest()
origin={}
def add(rel,pb):
    f=out/rel
    if isinstance(pb,Path):
        raw=pb.read_bytes();key=str(pb.relative_to(O));origin[key]=digest(raw)
    else:raw=pb
    if rel.endswith('.gz'):f.write_bytes(gzip.compress(raw,compresslevel=6,mtime=0))
    else:f.write_bytes(raw)
    assert f.stat().st_size<8*2**20
for m in ('check','build','test'):
    add(m+'-input-copy.json',O/m/'final-v4/copied.json')
    add(m+'-initial-wire.json.gz',O/m/'final-v4/initial-census.json')
    for t in ('first','second'):
        u=ex['rows_for'](m,'final-v4',t)
        data=(json.dumps(u,sort_keys=True,indent=2)+'\n').encode()
        orig=u['protocol-original-shas']
        for n,sha in orig.items():assert h(O/m/'final-v4'/t/n)==sha
        add(m+'-'+t+'.json.gz',data)
        for n,sha in orig.items():origin[str((O/m/'final-v4'/t/n).relative_to(O))]=sha
add('changed-headers.json',O/'changed-rmeta-headers-v4.json')
add('changed-elf.json',O/'changed-all-elf-v4.json')
native=json.loads((O/'changed-all-elf-v4.json').read_bytes())
for m,items in native.items():
    for label,v in items.items():
        if not v['is_test_harness']:continue
        base=O/'changed-all-elf-v4'/(m+'-'+v['case_id'])
        for f in sorted(base.iterdir()):
            if f.name=='result.json':continue
            assert re.fullmatch(r'(stock-repeat|final-v4)-(list|filter-[0-2])\.(stdout|stderr)',f.name),f
            add('native-'+m+'-'+v['case_id']+'-'+f.name+'.gz',f)
save(out/'originals.json',origin)
