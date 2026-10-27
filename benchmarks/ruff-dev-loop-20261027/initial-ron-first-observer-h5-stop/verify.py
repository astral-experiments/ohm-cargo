"""Check every retained original timing and the separately rejected triplet, without estimating effects."""
from pathlib import Path
import csv,json,gzip,hashlib
p=Path(__file__).resolve().parent;x=json.loads(gzip.decompress((p/'receipts.json.gz').read_bytes()))
f=p/'stopped.csv';assert hashlib.sha256(f.read_bytes()).hexdigest()==x['file_sha256'] and x['rc']==1
rows=list(csv.DictReader(f.open()));assert len(rows)==0
for row in rows:
    name=f"score-{int(row['block']):02d}-{row['slot']}-{row['arm']}"
    for phase in ('cold','first','settled'):
        v=x['slots'][name][phase];assert v['summary']['elapsed_ns']==v['status']['elapsed_ns']==int(row[phase+'_ns'])
        assert v['status']['rc']==0 and len(v['native'])==110
failed=x['slots']['score-01-1-D'];assert len(x['slots'])==1
assert [failed[k]['summary']['fresh'] for k in ('cold','first','settled')]==[0,563,619]
assert [failed[k]['summary']['checksums'] for k in ('cold','first','settled')]==[0,45,45]
assert [failed[k]['status']['rc'] for k in ('cold','first','settled')]==[0,0,0]
before,after,settled=[failed[k]['native'] for k in ('cold','first','settled')];assert after==settled and len(after)==110
bad=[]
for f0 in before:
    a,b=before[f0],after[f0]
    if a==b:continue
    assert a['bytes']==b['bytes'] and a['except_registered_wild_fields']==b['except_registered_wild_fields']
    if not {a['rodata_entsize'],b['rodata_entsize']}<={0,8}:bad.append(f0)
assert len(bad)==1
orig=before[bad[0]];now=after[bad[0]];real=json.loads((p/'real.json').read_bytes())
assert (orig['raw'],now['raw'])==(real['from']['sha256'],real['to']['sha256'])
assert real['from']['entsize']==0 and real['to']['entsize']==1 and len(real['differing_raw_byte_offsets'])==33
assert len(real['ordinary_callers'])==2 and real['ordinary_callers'][0]==real['ordinary_callers'][1] and real['ordinary_callers'][0]['passed']
assert "ruff_python_parser/" in bad[0] and real["ordinary_callers"][0]["listed"]>0
print("Zero accepted observations. The first stock-only triplet returned 0 three times and failed the original ELF width rule.")
