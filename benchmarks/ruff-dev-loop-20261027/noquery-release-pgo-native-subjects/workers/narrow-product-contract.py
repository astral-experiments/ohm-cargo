"""Verify unmodified baseline files against the prospective timing-artifact admission contract."""
from pathlib import Path
import hashlib,json,re,struct
X=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-pinned-20261028')
labels=('seed','A','A-repeat','Q','N');h=lambda b:hashlib.sha256(b).hexdigest()
def elf(p):
 raw=p.read_bytes();assert raw[:7]==b'\x7fELF\x02\x01\x01'
 start=struct.unpack_from('<Q',raw,40)[0];size,count,names=struct.unpack_from('<HHH',raw,58);assert size==64
 heads=[struct.unpack_from('<IIQQQQIIQQ',raw,start+i*size) for i in range(count)];n=heads[names];nt=raw[n[4]:n[4]+n[5]]
 c=lambda st,at:st[at:st.index(b'\0',at)]
 sections={c(nt,v[0]).decode():v for v in heads};section=lambda name:raw[sections[name][4]:sections[name][4]+sections[name][5]]
 sym=section('.symtab');st=section('.strtab');rows=[]
 for i in range(0,len(sym),24):
  op,binding,other,sect,value,sbytes=struct.unpack_from('<IBBHQQ',sym,i)
  rows.append((c(st,op),binding,other,sect,value,sbytes))
 norm=bytearray(raw)
 geno=sections['.note.gnu.build-id'];bn=section('.note.gnu.build-id')
 assert struct.unpack_from('<III',bn)==(4,32,3) and bn[12:16]==b'GNU\0' and len(bn)==48
 norm[geno[4]+16:geno[4]+48]=bytes(32)
 assert sections['.strtab'][2]&2==0
 llvm=[]
 for m in re.finditer(rb'\.llvm\.([0-9]+)\x00',st):
  si=sections['.strtab'][4]+m.start(1);en=sections['.strtab'][4]+m.end(1);norm[si:en]=b'0'*(en-si)
  llvm.append((m.start(1),m[1].decode()))
 return raw,st.split(b'\0'),rows,section('.dynstr'),h(bytes(norm)),llvm
records={};raws={}
for key in labels:
 result=elf(X/key/'cargo')
 if key in ('seed','A','A-repeat'):raws[key]=result
 records[key]={'raw_sha':h(result[0]),'bytes':len(result[0]),'entire_file_after_fixed_fields_masked_sha256':result[4],'original_llvm_string_suffixes':len(result[5])}
original={};base='A'
for left,right in (('seed','A'),('A','A-repeat'),('seed','A-repeat')):
 lraw,lst,lsy,ldy,lnorm,ll=raws[left];rraw,rst,rsy,rdy,rnorm,rl=raws[right]
 assert lraw!=rraw and lnorm==rnorm and ldy==rdy and len(lst)==len(rst) and len(lsy)==len(rsy)
 changed=[];binds={}
 for i,(a,b) in enumerate(zip(lsy,rsy)):
  assert a[1:]==b[1:]
  if a[0]==b[0]:continue
  l=re.fullmatch(rb'(.+)\.llvm\.([0-9]+)',a[0]);r=re.fullmatch(rb'(.+)\.llvm\.([0-9]+)',b[0]);assert l and r and l[1]==r[1] and len(l[2])==len(r[2]) and a[0]+b'\x00' not in ldy and b[0]+b'\x00' not in rdy,(i,a,b)
  changed.append({'symtab_index':i,'old':a[0].decode(),'new':b[0].decode(),'binding':a[1]>>4,'info':a[1],'other':a[2],'section_index':a[3],'value':a[4],'bytes':a[5]});binds[a[1]>>4]=binds.get(a[1]>>4,0)+1
 assert len(changed)==142 and binds=={0:53,1:89}
 assert sum(x!=y for x,y in zip(lst,rst))==142
 original[left+'--'+right]={'symtab_changes':changed,'full_symbols':len(lsy),'strtab_roster':len(lst),'differing_bindings':binds,'whole_raw_equal':False,'unchanged_entire_file_except_number_suffixes_and_build_id':True,'identical_dynamic_names':True}
out={'schema':1,'stages':records,'pairs':original};dest=X/'complete-symbol-deltas.json';dest.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps(records),h(dest.read_bytes()),flush=True)
