"""Check Rust/LLVM local symbol suffixes and the equivalent link output in two full builds."""
from pathlib import Path
import struct,hashlib,json,sys,re,collections
X=Path('/mnt/devbox-scratch/dev-user/ohm-producer-attestation-pinned-20261028');arms=sys.argv[1:]
assert len(arms)==2
def sha(b):return hashlib.sha256(b).hexdigest()
def inventory(path):
 b=path.read_bytes();p=struct.unpack_from('<Q',b,40)[0];size,n,nm=struct.unpack_from('<HHH',b,58)
 sections=[struct.unpack_from('<IIQQQQIIQQ',b,p+i*size) for i in range(n)];h=sections[nm];names=b[h[4]:h[4]+h[5]]
 def c(buf,off):return buf[off:buf.index(b'\0',off)].decode()
 sec={c(names,h[0]):h for h in sections};data=lambda k:b[sec[k][4]:sec[k][4]+sec[k][5]]
 strtab=data('.strtab');sym=data('.symtab');dynstr=data('.dynstr');count=len(sym)//24;syms=[]
 for i in range(count):
  ofs,info,other,sect,addr,sz=struct.unpack_from('<IBBHQQ',sym,24*i)
  syms.append((c(strtab,ofs),info,other,sect,addr,sz))
 return {'bytes':b,'sections':{k:{'offset':h[4],'size':h[5],'type':h[1],'alloc':bool(h[2]&2),'digest':sha(data(k)) if h[1]!=8 else None} for k,h in sec.items()},'names':strtab.split(b'\0'),'symbols':syms,'dynstr':dynstr}
def decoded(a,b):
 if a==b:return 'identical'
 l=re.fullmatch(rb'(.+)\.llvm\.([0-9]+)',a);r=re.fullmatch(rb'(.+)\.llvm\.([0-9]+)',b)
 if l and r and l[1]==r[1]:return 'llvm-internal-suffix'
 l=re.fullmatch(rb'(.+\.)([a-z0-9]+)(\.rcgu\.o)',a);r=re.fullmatch(rb'(.+\.)([a-z0-9]+)(\.rcgu\.o)',b)
 if l and r and l[1]==r[1]:return 'cgu-temp-name'
 return 'other'
a,b=(inventory(X/z/'cargo') for z in arms)
assert set(a['sections'])==set(b['sections'])
assert a['dynstr']==b['dynstr']
assert len(a['symbols'])==len(b['symbols'])
kinds=collections.Counter();group=collections.Counter();other=[]
for x,y in zip(a['symbols'],b['symbols']):
 assert x[1:]==y[1:] # type, binding, section, symbol address, length
 kind=decoded(x[0].encode(),y[0].encode());kinds[kind]+=1
 if kind!='identical':
  group[(kind,x[1]>>4)]+=1
  if kind=='other':other.append([x[0],y[0]])
end={k:(a['sections'][k]['digest']==b['sections'][k]['digest']) for k in a['sections']}
z={'arms':arms,'elf_sha256':[sha(a['bytes']),sha(b['bytes'])],'whole_identical':a['bytes']==b['bytes'],'bytes':[len(a['bytes']),len(b['bytes'])],'raw_differing_sections':[k for k,v in end.items() if not v],'changing_allocated_sections':[k for k,v in end.items() if not v and a['sections'][k]['alloc']],'same_mapped_machine_sections':all(end[k] for k in ('.text','.rodata','.data','.bss','.dynstr','.dynsym','.rela.dyn','.eh_frame')),'symbols':dict(kinds),'differing_symbol_bindings':[[k,b,n] for (k,b),n in group.items()],'all_symbol_addresses_types_sizes_equal':True,'different_unclassified_symbol_names':other,'source_strtab_sequence_lengths':[len(a['names']),len(b['names'])]}
if len(a['names'])==len(b['names']):z['string_kinds']=dict(collections.Counter(decoded(x,y) for x,y in zip(a['names'],b['names'])))
save=X/('symbol-equivalence-'+'-'.join(arms)+'.json');save.write_text(json.dumps(z,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in z.items() if k!='different_unclassified_symbol_names'}),flush=True);print('other name differences',len(other),other[:1])
