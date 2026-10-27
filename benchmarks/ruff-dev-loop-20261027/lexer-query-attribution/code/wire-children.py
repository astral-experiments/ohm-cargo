"""Read H5's already frozen parser metadata snapshots without copying any native study files."""
from pathlib import Path
import hashlib,json,subprocess,sys
d=Path(__file__).resolve().parent
s=(d.parent/'metadata-tables.py').read_text()
end=s.index("    keys=entries(tables['def_path_hashes'])")
s=s[:end]+'''    def ident(i):
      r.i=entries(tables["def_keys"])[i]
      parent=r.u(); assert parent==1;parent=r.u();ns=r.u();assert ns in [5,6],ns
      n=r.sym();assert isinstance(n,str) and r.u()==0;return n
    keys=entries(tables["def_path_hashes"]);idx,=[i for i,k in enumerate(keys)if k==target_module]
    assert ident(idx)=="lexer";out={"root_local_key":f"{target_module:016x}","crate":name}
    for kind in ("module_children_non_reexports","module_children_reexports"):
      table=entries(tables[kind]);slot=table[idx]if idx<len(table)else 0
      raw=slot.to_bytes(16,"little");at=int.from_bytes(raw[::2],"little");n=int.from_bytes(raw[1::2],"little")
      assert n<50 and (at or not n);r.i=at
      if kind=="module_children_reexports":
       out[kind]=n;continue
      seq=[r.u()for _ in range(n)]
      out[kind]=[{"item":ident(i),"local_id":f"{keys[i]:016x}","defindex":i,"ident_span":lookup_span(entries(tables["def_ident_span"])[i]),"def_kind":entries(tables["def_kind"])[i],"visibility_discriminant":m[entries(tables["visibility"])[i]]} for i in seq]
    return out
'''
s=s.replace('def decode(path):','def decode(path,target_module):')
s+='''
import hashlib,sys
r=Path.home()/'.cache/ohm-233-position-qualified-20261027/pr233-h5-private-parser-witness-v2'
m={}
for case in sys.argv[1:]:
 mode,arm=case.split('/');m[case]={}
 for phase in ('original-baseline','lexer-pending-indentation-edit','lexer-pending-indentation-restore'):
  q=r/case/phase
  if not (q/'record.json').exists():continue
  p,=q.glob('*.rmeta');b=p.read_bytes();data=decode(p,int(('b572ff01c439e1cb' if mode=='build' else '72571c268fc89bf9'),16))
  rows=data['module_children_non_reexports'];assert [e['item']for e in rows]==['lex','Lexer'],rows;assert all(e['visibility_discriminant']==0 for e in rows);assert data['module_children_reexports']==0
  rec=json.loads((q/'record.json').read_bytes());h=hashlib.sha256(b).hexdigest();assert h in json.dumps(rec),(case,phase,'unbound metadata')
  data.update(rmeta_sha256=h,parent_receipt_sha256=hashlib.sha256((q/'record.json').read_bytes()).hexdigest());m[case][phase]=data
print(json.dumps(m))
'''
o=json.loads(subprocess.check_output(['dbox','ssh','charlie-ohm-loader-perf-1024','--no-tmux','--','nice','-n','19','taskset','-c','31','/usr/bin/python3','-B','-c',s,*sys.argv[1:]],timeout=120))
for c,r in o.items():
 p=d/'wire'/c;p.mkdir(parents=True,exist_ok=True);(p/'module-children.json').write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
 print(c,[(k,[(i['item'],i['ident_span'],i['visibility_discriminant'])for i in v['module_children_non_reexports']])for k,v in r.items()])
