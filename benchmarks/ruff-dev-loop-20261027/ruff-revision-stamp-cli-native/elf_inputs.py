"""Look for the native execution that an ELF-name-only Rust build cache would need to cover."""
from pathlib import Path
import collections,json,re,struct,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
r=json.loads((q/'macro-guard/ruff-head-A/result.json').read_bytes());a=r['binary_dep_dynamic'];d=q/'macro-dso-survey';d.mkdir()
assert len(a)==23
def run(cmd):return subprocess.check_output(cmd,text=True,env=env)
rows=[]
for k in a:
 f=Path(k); raw=f.read_bytes();assert raw[:5]==b'\x7fELF\2'and raw[5]==1
 shoff=struct.unpack_from('<Q',raw,40)[0];esize,count,si=struct.unpack_from('<HHH',raw,58);unpack=lambda i:struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*esize)
 strings=unpack(si);st=raw[strings[4]:strings[4]+strings[5]];sects={}
 for j in range(count):
  x=unpack(j);n=st[x[0]:].split(b'\0',1)[0].decode();sects[n]=x
 dyn=run(['readelf','-dW',f]);rel=run(['readelf','-rW',f]);nm=run(['nm','-an',f]);syms={}
 for line in nm.splitlines():
  el=line.split(maxsplit=2)
  if len(el)==3 and re.fullmatch('[0-9a-fA-F]+',el[0]):syms.setdefault(int(el[0],16),[]).append(el[2])
 addr=sects['.init_array'][3];length=sects['.init_array'][5];offset=sects['.init_array'][4]
 ar=[]
 for pos in range(0,length,8):
  loc=addr+pos;val=struct.unpack_from('<Q',raw,offset+pos)[0];rr=next((x.split()for x in rel.splitlines()if re.match(r'^0*'+format(loc,'x')+' ',x)),None)
  if rr and len(rr)==4 and rr[2]=='R_X86_64_RELATIVE':val=int(rr[3],16)
  ar.append([hex(loc),hex(val),syms.get(val,[]),rr])
 rec={'basename':f.name,'sha':H(raw),'bytes':len(raw),'init_functions':ar,'init':[(n,hex(sects[n][3]),sects[n][5])for n in('.init','.preinit_array','.init_array','.fini','.fini_array')if n in sects],'dynamic_tags':[[m[1],m[2].strip()]for line in dyn.splitlines()if(m:=re.search(r'\((NEEDED|INIT|INIT_ARRAY|PREINIT_ARRAY|FINI|FINI_ARRAY|AUDIT|DEPAUDIT|RPATH|RUNPATH|FILTER|AUXILIARY|FLAGS|FLAGS_1)\)\s*(.*)',line))],'ifunc_relocations':sum('IRELATIVE'in x or 'IRELATIV'in x for x in rel.splitlines()),'dynamic_ifunc_symbols':sum('IFUNC'in x for x in run(['readelf','--dyn-syms','-W',f]).splitlines()),'other_relocation_types':sorted(set(re.findall(r'R_X86_64_\w+',rel)))};rows.append(rec)
put(d/'records.json',rows);print(len(rows),sum(r['bytes']for r in rows),collections.Counter(len(x['init_functions'])for x in rows));print(collections.Counter(n[0]if n else '<unknown>'for r in rows for _,_,n,_ in r['init_functions']));print(collections.Counter(v for r in rows for tag,v in r['dynamic_tags']if tag=='NEEDED'));print('ifunc',sum(r['ifunc_relocations']+r['dynamic_ifunc_symbols']for r in rows))
