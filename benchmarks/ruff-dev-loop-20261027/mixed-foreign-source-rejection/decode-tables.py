"""Decode the dense producer source table of this fixture, checking every index against its serialized filename."""
import hashlib,json,re
from pathlib import Path
import sys
p=Path(sys.argv[1]); out=Path(sys.argv[2]); dct={}
for n in ['short','long','short-restored']:
 f=p/(n+'.rmeta');raw=f.read_bytes();ent=[]
 for m in re.finditer(rb'\x00\x00([\x0e\x0f\x12])(leaf/src/(?:p[0-9]|lib|macros)\.rs)',raw):
  assert m[1][0]==len(m[2]);ent.append({'index':len(ent),'source':m[2].decode(),'entry_offset':m.start()})
 assert len(ent)==(11 if n=='long' else 2)
 tab=b''.join(x['entry_offset'].to_bytes(2,'little') for x in ent); at=raw.find(tab)
 assert at>ent[-1]['entry_offset'] and at==raw.rfind(tab);assert [int.from_bytes(raw[at+2*i:at+2*i+2],'little')for i in range(len(ent))]==[x['entry_offset']for x in ent]
 dct[n]={'sha256':hashlib.sha256(raw).hexdigest(),'table_offset':at,'width':2,'entries':ent}
out.write_text(json.dumps(dct,indent=2)+'\n')
