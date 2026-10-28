"""Account for raw independent cold differences, including the Rust wire structure and real archive symbol index."""
from pathlib import Path
import hashlib,itertools,json,os,re,subprocess,sys
W=Path.home()/'.cache/ohm-script-hash-wall-rc19-v1';C=W/'current';host=os.uname().nodename;H=Path.home();env={**os.environ,'RUSTUP_HOME':str(W/'rustup')};sha=lambda b:hashlib.sha256(b).hexdigest();rd=lambda f:json.loads(f.read_bytes());dest=W/'secure-product-oracle-v2';dest.mkdir()
def get(role):
 if role.startswith('S'):
  r=W/'additional-stock-cold-v1'/('reference-'+role[1:]);return{q:(r/('libty_vendored'+q)).read_bytes()for q in ('.rlib','.rmeta')}
 q=rd(W/'reports'/('secure-pre-'+role+'.json'));out={}
 for n,k in q['products'].items():
  rel=Path(n).relative_to(C)
  possibles=[W/'states'/role,C,W/'additional-stock-cold-v1'/('untouched-'+role),W/'stable-adversaries-v3'/(role+'-ordinary')]
  for rr in possibles:
   if (rr/rel).is_file():
    b=(rr/rel).read_bytes()
    if sha(b)==k:out[rel.suffix]=b;break
 assert len(out)==2,(role,list(out));return out
def archive(b):
 assert b[:8]==b'!<arch>\n';i=8;names=None;out=[]
 while i<len(b):
  d=b[i:i+60];assert d[-2:]==b'`\n';n=int(d[48:58]);raw=b[i+60:i+60+n];name=d[:16].strip().decode();pad=b[i+60+n:i+60+n+n%2]
  if name=='//':names=raw
  elif name.startswith('/')and name[1:].isdigit():
   j=int(name[1:]);name=names[j:names.index(b'/\n',j)].decode()
  elif name not in ('/','/SYM64/'):name=name.removesuffix('/')
  out.append((name,d,raw,pad));i+=60+n+n%2
 assert i==len(b);return out
def wire(b):
 assert b[-13:]==b'rust-end-file';r=int.from_bytes(b[8:16],'little');g=len(b)-29;assert b[g-9:g]==bytes.fromhex('01910108069101033f');tbls=[]
 for total in (12+17*k for k in range(4)):
  es=r-total;ls=es-63;t={}
  for start,length,end,kind in [(ls,8,es,'local'),(es,3,r,'expn')]:
   bitmap=int.from_bytes(b[start:start+8],'little');first=int.from_bytes(b[start+8:start+12],'little')
   if first!=0 or bitmap>=1<<length or 12+17*bitmap.bit_count()!=end-start:break
   for j,ind in enumerate(i for i in range(length)if bitmap&(1<<i)):
    pos=start+12+17*j
    if b[pos]!=1:break
    t[(kind,ind)]=pos+1
   else:continue
   break
  else:tbls.append(t)
 assert len(tbls)==1;d=tbls[0];d[('public_global_hash',None)]=g;return d
roles=list('AB')
if 'loader-'in host:
 assert (W/'additional-stock-cold-v1/complete.json').is_file();roles+=['S0','S1']
raw={k:get(k)for k in roles};dump={};out={};ds={}
for k,v in raw.items():
 p=dest/(k+'.rmeta');p.write_bytes(v['.rmeta']);dump[k]=subprocess.check_output([H/'.cargo/bin/rustc','+ohm','-Zls=root',p],env=env,text=True).splitlines();ds[k]={ext:sha(bytes_)for ext,bytes_ in v.items()}
for ka,kb in itertools.combinations(roles,2):
 a,b=raw[ka]['.rmeta'],raw[kb]['.rmeta'];n=len(a);assert n==len(b);dw=wire(a);assert dw==wire(b)
 rep=bytearray(a);fields=[];assert len(dump[ka])==len(dump[kb])
 for one,two in zip(dump[ka],dump[kb]):
  hx=r'\b[0-9a-f]{32}\b';label=re.sub(hx,'{hash}',one);assert label==re.sub(hx,'{hash}',two)
  for u,v in zip(re.findall(hx,one),re.findall(hx,two)):
   if u==v:continue
   hits=[]
   for tr in [lambda s:s,lambda s:s[::-1],lambda s:s[:8][::-1]+s[8:][::-1],lambda s:s[8:]+s[:8]]:
    x,y=map(lambda s:tr(bytes.fromhex(s)),(u,v));i=a.find(x)
    if i>=0 and a.count(x)==1 and b[i:i+16]==y:hits.append((i,x,y))
   assert len(hits)==1,(ka,kb,label,len(hits));i,x,y=hits[0];rep[i:i+16]=y;fields.append({'source':label,'offset':i,'A':u,'B':v})
 for (kind,ind),i in dw.items():
  if a[i:i+16]!=b[i:i+16]:
   assert (kind,ind)in [('local',0),('local',7),('public_global_hash',None)],(ka,kb,kind,ind)
   fields.append({'source':kind,'index':ind,'offset':i,'A':a[i:i+16].hex(),'B':b[i:i+16].hex()});rep[i:i+16]=b[i:i+16]
 assert rep==b,(ka,kb,'unaccounted metadata byte')
 aa,bb=map(archive,[raw[ka]['.rlib'],raw[kb]['.rlib']]);assert len(aa)==len(bb)==7
 names={x[0]:y[0]for x,y in zip(aa,bb)if x[0].endswith('.rcgu.o')};assert len(names)==3
 for u,v in names.items():
  uu=u.split('.');vv=v.split('.');assert uu[:-3]+uu[-2:]==vv[:-3]+vv[-2:] and all(re.fullmatch('[a-z0-9]{7}',kk[-3])for kk in [uu,vv])
 mem=[]
 for (nm,h1,x,p1),(nm2,h2,y,p2) in zip(aa,bb):
  assert h1==h2 and p1==p2 and (nm2==nm or names[nm]==nm2);kind=nm;rx=x
  if nm in names:kind='ELF codegen unit';assert x.startswith(b'\x7fELF')and y==x
  elif nm=='/':assert x==y
  elif nm in ('//','lib.rmeta-link'):
   for name,new in names.items():rx=rx.replace(name.encode(),new.encode())
  elif nm=='lib.rmeta':
   assert x.count(a)==y.count(b)==1;rx=x.replace(a,b)
  else:raise AssertionError(nm)
  assert rx==y;mem.append({'kind':kind,'before':sha(x),'after':sha(y),'header':sha(h1),'size':len(x)})
 out[ka+'-'+kb]={'metadata_fields':fields,'raw_different_bytes':sum(i!=j for i,j in zip(a,b)),'archive_members':mem,'archive_name_map':names,'complete_byte_accounting':True}
print(json.dumps({'host':host,'roles':ds,'pairs':out,'qualified':True},sort_keys=True))
