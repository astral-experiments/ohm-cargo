"""Check every retained original timing and the separately rejected triplet, without estimating effects."""
from pathlib import Path
import csv,json,gzip,hashlib
p=Path(__file__).resolve().parent;x=json.loads(gzip.decompress((p/'receipts.json.gz').read_bytes()))
f=p/'stopped.csv';assert hashlib.sha256(f.read_bytes()).hexdigest()==x['file_sha256'] and x['rc']==1
rows=list(csv.DictReader(f.open()));assert len(rows)==6
for row in rows:
    name=f"score-{int(row['block']):02d}-{row['slot']}-{row['arm']}"
    for phase in ('cold','first','settled'):
        v=x['slots'][name][phase];assert v['summary']['elapsed_ns']==v['status']['elapsed_ns']==int(row[phase+'_ns'])
        assert v['status']['rc']==0 and len(v['native'])==110
failed=x['slots']['score-03-1-A'];assert len(x['slots'])==7
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
ty=json.loads((p/'stock-widths.json').read_bytes());assert ty['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
for w in (1,2,4,8,16,32,64,128,256):
    e=ty['inputs'][str(w)];obs=e['observations'];assert e['output_widths']==[0,w] and len(obs)==4
    assert obs[0]==obs[2] and obs[1]==obs[3] and len({o['normalized'] for o in obs})==1 and len({o['elf_sha256'] for o in obs})==2
print('Six original slots preserved. Seventh failed original numeric native identity gate. Nine stock-only fixtures replicated.')
