"""Compare the native Cargo ELF and its original direct inputs across identical-source builds."""
import hashlib,json,struct,sys
from pathlib import Path
z=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-pinned-20261028');a,b=sys.argv[1:]
def sha(v):return hashlib.sha256(v).hexdigest()
def elf(p):
 raw=p.read_bytes(); assert raw[:7]==b'\x7fELF\x02\x01\x01'
 sh=struct.unpack_from('<Q',raw,40)[0];size,n,names=struct.unpack_from('<HHH',raw,58);assert size==64
 val=[struct.unpack_from('<IIQQQQIIQQ',raw,sh+size*i) for i in range(n)]
 hdr=val[names];labels=raw[hdr[4]:hdr[4]+hdr[5]]
 result={}
 for idx,h in enumerate(val):
  start=h[0];name=labels[start:labels.index(b'\0',start)].decode();payload=raw[h[4]:h[4]+h[5]] if h[1]!=8 else b''
  result[name]={'header':list(h[1:]),'sha256':sha(payload),'bytes':len(payload),'loadable':bool(h[2]&2)}
 return {'raw':sha(raw),'bytes':len(raw),'sections':result}
ar=elf(z/a/'cargo');br=elf(z/b/'cargo')
assert set(ar['sections'])==set(br['sections']); diff={}
for key in ar['sections']:
 l,r=ar['sections'][key],br['sections'][key]
 if l==r:continue
 diff[key]={'payload_equal':l['sha256']==r['sha256'],'bytes':[l['bytes'],r['bytes']],'different_header_fields':[i+1 for i,(x,y) in enumerate(zip(l['header'],r['header'])) if x!=y],'alloc':l['loadable']}
deps={st:json.loads((z/st/'actual-inputs.json').read_bytes()) for st in (a,b)}
own=[v['src/bin/cargo/main.rs']['externs']['cargo'] for v in deps.values()]
out={'comparison':[a,b],'arms':{a:ar,b:br},'differences':diff,'cargo_library':own}
(z/('elf-'+a+'-'+b+'.json')).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
print(ar['raw'],br['raw'], 'data changing', [(k,v['bytes'],v['alloc']) for k,v in diff.items() if not v['payload_equal']]);print('header only',[(k,v['different_header_fields']) for k,v in diff.items() if v['payload_equal']]);print([list(v.values()) for v in own])
