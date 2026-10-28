from pathlib import Path
import gzip,hashlib,json
D=Path(__file__).resolve().parent;R=D/'receipts';V=R/'private-registry-h8-v2';j=lambda p:json.loads(p.read_bytes());h=lambda b:hashlib.sha256(b).hexdigest();a=j(D/'amendment.json');failure=j(R/'rejected-v1-diagnostic.json');r=j(V/'reconstruction.json');w=j(V/'initialization-replay/matched.json');t=r['test_files'];prefix='/home/dev-user/.cache/ohm-output-path-ruff-20261028/cargo-home/.ohm-registry-json-v2/'
for mode,m in [('workspace',w),('test',t)]:
 d=h(json.dumps({prefix+k:v for k,v in m.items()},separators=(',',':'),sort_keys=True).encode());assert a['registry'][mode]==[len(m),d] and a['registry'][mode]==failure[mode]['proof_native']['.ohm-registry-json-v2'];v=failure[mode];assert not v['scored_rows'] and not any(v[k] for k in ('added','changed_dot_d','changed_product_stamps','missing'))
assert r['original_zeros'] and r['workspace_before'][0]==773 and r['workspace_recreated'][0]==774 and r['retained']==a['registry']['test'];assert j(V/'initialization-replay/result.json')['recovered'][0]==773
assert j(V/'initialization-replay/exact-selection.json')[0]==['526','58a',w['526'],w['58a']];files=sorted(V.rglob('record.json.gz'));assert len(files)==10
for f in files:
 v=json.loads(gzip.decompress(f.read_bytes()));assert v['rc']==0 and len(v['physical'])==2 and v['units'] in (501,619)
for m in ('parent','candidate'):assert a['original_failure']==h((R/'rejected-v1-diagnostic.json').read_bytes())
assert a['phase_worker']==h((D/'run-h8-isolated.py').read_bytes()) and a['activation_helper']==h((D/'recover-registry.py').read_bytes());print('10 native reconstructions, both original registry path+byte hashes, zero H8 scored observations')
