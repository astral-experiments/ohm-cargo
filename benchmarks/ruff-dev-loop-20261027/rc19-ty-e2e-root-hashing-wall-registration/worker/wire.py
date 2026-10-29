"""Retain the complete compiler recipe and verify each variable field against independent native evidence."""
import os,re,hashlib,stat
from pathlib import Path
from common import K,E2E,INC,NAME,rawsha,get,put,datafile,signature,DESIGN
from cfg_decode import Decoder
from cfg_source import select_files,bind
SESS=re.compile(r'(s-[0-9a-z]{10}-[0-9a-z]{7})-working')
def sha(b):return hashlib.sha256(b).hexdigest()
def num(n):
 assert n>=0;out=bytearray()
 while n>=128:out.append(128|(n&127));n>>=7
 out.append(n);return bytes(out)
def enc(s):b=os.fsencode(s);return num(len(b))+b+b'\xc1'
def disk(p):
 a=p.lstat();assert stat.S_ISREG(a.st_mode)
 with os.fdopen(os.open(p,os.O_RDONLY|os.O_NONBLOCK|os.O_NOATIME|os.O_NOFOLLOW),'rb')as h:
  b=h.read();z=os.fstat(h.fileno())
 assert (z.st_ino,z.st_dev,z.st_ctime_ns,z.st_size)==(a.st_ino,a.st_dev,a.st_ctime_ns,len(b));return b

def keep(directory,body):
 name=sha(body);directory.mkdir(exist_ok=True);p=directory/name
 if p.exists():assert disk(p)==body
 else:
  with p.open('xb')as f:f.write(body)
  assert rawsha(p)==name
 return name

def acquire(d,when):
 p=E2E.with_suffix('.rlink');result={'path':str(p),'existence':'absent'}
 if os.path.lexists(p):
  b=disk(p);result={'path':str(p),'existence':'regular','length':len(b),'sha256':keep(K/'raw-recipes',b)}
 put(d/('raw-recipe-'+when+'.json'),result);return result

def normalize(body,ranges):
 out=bytearray();last=0
 for lo,hi,old,new,_kind in ranges:
  assert last<=lo<hi<=len(body) and body[lo:hi]==old;out+=body[last:lo]+new;last=hi
 out+=body[last:];return bytes(out)

def invert(body,ranges,wire):
 out=bytearray();last=0;pos=0
 for lo,hi,old,new,_ in ranges:
  n=lo-last;out+=wire[pos:pos+n];pos+=n;assert wire[pos:pos+len(new)]==new;out+=old;pos+=len(new);last=hi
 out+=wire[pos:];assert bytes(out)==body

def bind_source_files():
 files=select_files();assert {str(owner):{k:v for k,v in f.items()if k!='data'} for owner,f in files.items()}==get(DESIGN/'cfg-sources.json');return files

def check(body,ledger,expected,inc_dir,obj_dir,native_inputs=None,scope=None):
 assert sha(body)==ledger['source_sha256'] and body.startswith(b'rustlink\x00\x00\x00\x01')
 cfg=Decoder(body).run();assert cfg['root']=='e2e' and cfg['indexed_crates']==233 and set(cfg['libraries'])=={'5','7','146'}
 sources=bind_source_files();bases,spans=bind(cfg,sources,body,num);assert bases[7]-bases[5]==90107
 rg=Decoder(body);assert rg.take(12)==b'rustlink\x00\x00\x00\x01';assert '(ca780121c 'in rg.string();count=rg.num();assert count==138
 fields={f[0]:f[1:] for f in ledger['authentic_object_name_fields']};patch=[];rows=[];tokens=set();cgus=set();mask=[]
 def fld(i,j,new,kind):patch.append((i,j,body[i:j],new,kind))
 for index in range(count+1):
  if index==count:assert rg.tag(2)==1
  start=rg.pos;cgu=rg.string();assert re.fullmatch(r'[a-z0-9]{25}',cgu) and cgu not in cgus;cgus.add(cgu);assert rg.tag(2)==int(index==count) and rg.tag(2)==1
  current=Path(rg.string());basename=current.name;stem,c,tok,rcgu,ext=basename.split('.');assert (stem,c,rcgu,ext)==(NAME,cgu,'rcgu','o') and re.fullmatch(r'[a-z0-9]{7}',tok)
  assert current.parent==E2E.with_suffix('.rlink-objects');pos=rg.pos-1-len('.rcgu.o')-7;nonce,name,size,checksum=fields.pop(pos);assert nonce==tok and name==basename and body[pos:pos+7]==tok.encode();tokens.add(tok);fld(pos,pos+7,b'NoncE00','verified-object-filename')
  real=obj_dir/basename;fp=datafile(real);assert (fp['size'],fp['sha256'])==(size,checksum)
  if native_inputs is not None:assert native_inputs[str(current)]==(size,checksum)
  assert [rg.tag(2) for _ in range(5)]==[0]*5
  begin=rg.pos;v=rg.num();assert v in (0,1);row={'cgu':cgu,'name':basename,'size':size,'sha':checksum,'kind':'allocator'if index==count else'regular','index':index,'cache_sources':v}
  if v:
   original=Path(rg.string());m=SESS.fullmatch(original.parent.name);assert m and original.parent.parent==INC and original.name==cgu+'.o'
   siblings=[v for v in inc_dir.glob(m[1]+'-*') if v.is_dir() and not v.is_symlink() and re.fullmatch(re.escape(m[1])+'-[a-z0-9]{25}',v.name)];final,=siblings;assert (inc_dir/(m[1]+'.lock')).is_file()
   projected=final/original.name;slot=datafile(projected);assert slot==fp and projected.samefile(real)
   a=projected.stat();row.update(cache_lexical=str(original),cache_incr_committed=final.name,dev=a.st_dev,ino=a.st_ino)
  mask.append(v);fld(begin,rg.pos,b'\x00','declared-incremental-source-vector');rows.append(row)
 assert len(rows)==139 and not fields and len(tokens)==1 and rg.pos==cfg['crate_info_start'];token,=tokens
 suffix=enc(str(E2E.with_suffix('.rlink-objects')))+b'\x01'+enc(token)+b'\x00\x00\x02\x02\x00\x03\x00rust-end-file';assert body.endswith(suffix)
 pos=len(body)-len(suffix)+len(enc(str(E2E.with_suffix('.rlink-objects'))))+2;assert body[pos:pos+7]==token.encode();fld(pos,pos+7,b'NoncE00','validated-OutputFilenames-invocation_temp');patch.sort()
 strict=normalize(body,patch);invert(body,patch,strict)
 for span in spans:
  a,b=span['offset'],span['end'];new=num(span['lo']-bases[5])+num(span['hi']-bases[5]);fld(a,b,new,'source-local-native-cfg-endpoints')
 patch.sort();general=normalize(body,patch);invert(body,patch,general);assert sha(general)==expected['all_histories_wire'] and len(general)==169094
 assert [[a['cgu'],a['kind'],a['size'],a['sha']] for a in rows]==expected['objects']
 obs={'body':sha(body),'length':len(body),'raw_cgus':rows,'raw_cfg':[[s['lo'],s['hi']] for s in spans],'settings':cfg['libraries'],'all_histories_wire':sha(general),'same_history_wire':sha(strict),'same_history_length':len(strict),'source_bases':bases,'cache_mask':mask,'absolute_current_object_identifiers':signature(ledger['objects']),'raw_span_ledger':spans,'reversible_ranges':[[a,b,sha(old),new.hex(),k]for a,b,old,new,k in patch]}
 if scope:
  obs['canonical_file']=keep(K/'comparison-recipes',general);obs['history_file']=keep(K/'comparison-recipes',strict)
 return obs

def prove(d,mode,ledger,has_native):
 post=get(d/'raw-recipe-after.json');body=disk(K/'raw-recipes'/post['sha256']);assert sha(body)==post['sha256'] and len(body)==post['length']
 native=None
 if has_native:
  nr=get(d/'native.json');n,=[r for r in nr['events'] if r['role']=='stock-wild' and r['out']==str(E2E)];assert nr['process_exit'][str(n['pid'])]==0;native={r['path']:(r['size'],r['sha256']) for r in n['direct_file_operands']}
 expected=get(DESIGN/'whole-reference.json')['sources'][mode];proof=check(body,ledger,expected,INC,E2E.with_suffix('.rlink-objects'),native,scope=True);put(d/'wire-proof.json',proof)

def same(left,right):
 a,b=get(left/'wire-proof.json'),get(right/'wire-proof.json'); keys=('same_history_wire','same_history_length','cache_mask','raw_cfg','source_bases','all_histories_wire','absolute_current_object_identifiers','settings')
 assert all(a[k]==b[k] for k in keys),('same-source same-history mismatch',[k for k in keys if a[k]!=b[k]])
 new=K/'comparison-recipes';assert disk(new/a['history_file'])==disk(new/b['history_file']);assert all((K/'raw-recipes'/x['body']).is_file()for x in (a,b))
 return {k:a[k] for k in ('same_history_wire','all_histories_wire','absolute_current_object_identifiers')}
