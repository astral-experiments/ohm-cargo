from snapshot import *
import struct, time
from collections import Counter

def read(p):return json.loads(p.read_text())
def idmap(x):return dig(json.dumps(x,separators=(',',':'),sort_keys=True).encode())
def ar(h):return read(Y/'objects'/('ar-'+h+'.json'))['members']
def metadata(h):
 if h is None:return None
 head=read(Y/'objects'/('rmeta-'+h+'.json'))['header'];return {'public':re.search('public_hash (\\w+)', head)[1],'private':re.search('private hash (\\w+)',head)[1],'stable_id':re.search(r'StableCrateId\(([0-9]+)\)',head)[1]}
def role(x):return (x['package'],x['target'],tuple(x['kind']),tuple(sorted(x['files'])))
def shells(phase):
 d=Y/'receipts'/phase;rows=read(d/'artifacts.json');out={}
 for r in rows:
  if not r['local'] or not any(f.endswith('.rlib') for f in r['files']):continue
  k=role(r); assert k not in out or out[k]['files']==r['files'];out[k]=r
 return out

def projected_elf(h):
 dest=Y/'objects'/('section-projection-'+h+'.json')
 if dest.exists():return read(dest)
 categories={key:[] for key in ('allocated','instructions','alloc_relocations','debug')}
 with (Y/'objects'/h).open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as a:
  for m in ar(h):
   if not m['name'].endswith('.o') or not m['elf']:continue
   off=m['offset'];assert a[off:off+6]==b'\x7fELF\x02\x01';headers_at=struct.unpack_from('<Q',a,off+40)[0];shsize,n,stridx=struct.unpack_from('<HHH',a,off+58);assert n and stridx<n and shsize==64; hdr=[struct.unpack_from('<IIQQQQIIQQ',a,off+headers_at+shsize*i) for i in range(n)];s=hdr[stridx];strings=a[off+s[4]:off+s[4]+s[5]]
   for sh in hdr:
    ni,t,flags,_,p,sz,link,info,align,entsize=sh;name=strings[ni:strings.index(0,ni)].decode('utf-8','backslashreplace');ks=[]
    if flags&2:
     ks.append('allocated');
     if flags&4:ks.append('instructions')
    if t in (4,9) and info<n and hdr[info][2]&2:ks.append('alloc_relocations')
    if name.startswith(('.debug','.zdebug')):ks.append('debug')
    if not ks:continue
    value=[name,t,flags,sz,align,entsize,None if t==8 else dig(a[off+p:off+p+sz])]
    for k in ks:categories[k].append(value)
 data={k:{'sha256':idmap(sorted(v)),'sections':len(v),'bytes':sum(z[3]for z in v)} for k,v in categories.items()};write(dest,data);return data

def delta(left,right,section_names):
 la,ra=shells(left),shells(right);assert set(la)==set(ra);result=[]
 for k,x in la.items():
  y=ra[k]; archive=lambda row,ext:sorted(set(a['sha256'] for f,a in row['files'].items() if f.endswith(ext)));old,new=archive(x,'.rlib'),archive(y,'.rlib');mo,mn=archive(x,'.rmeta'),archive(y,'.rmeta')
  if not x['local'] or not old:continue
  assert len(old)==len(new)==1 and len(mo)<=1 and len(mn)<=1;k1,k2=old[0],new[0];aa,bb=ar(k1),ar(k2); obj1,obj2=([z for z in arm if z['name'].endswith('.o') and z['elf']]for arm in (aa,bb));assoc=lambda o: [(z['name'],z['sha256'])for z in o];ctr=lambda o:Counter(z['sha256']for z in o);mo=(mo or [None])[0];mn=(mn or [None])[0];nm=x['target'];z={'name':nm,'kind':x['kind'],'types':x['types'],'archive':[k1,k2],'rmeta':[mo,mn],'root':[metadata(mo),metadata(mn)],'all_members':[len(aa),len(bb)],'native_objects':[len(obj1),len(obj2)],'identical_object_payloads':sum((ctr(obj1)&ctr(obj2)).values()),'all_native_names_and_bytes_equal':assoc(obj1)==assoc(obj2),'all_native_payload_multisets_equal':ctr(obj1)==ctr(obj2),'ar_index_sha':[next((m['sha256']for m in a if m['name'] in ('/','/SYM64/')),None)for a in (aa,bb)],'native_roster_sha256':[idmap(assoc(obj1)),idmap(assoc(obj2))]}
  if nm in section_names:z['elf_sections']=[projected_elf(k1),projected_elf(k2)]
  result.append(z)
 return sorted(result,key=lambda m:(m['name'],m['kind']))

def symbols(phase):
 p=Y/'receipts'/phase; g=read(p/'programs.json'); binary=Y/'objects'/g['external_sha256'];q=sp.run(['nm','-n','-C','--defined-only',binary],capture_output=True,check=True);rows={}
 for name in ('is_empty_f_string','is_non_empty_f_string'):
  z=[s for s in q.stdout.decode(errors='replace').splitlines() if re.search(r' [tT] ruff_python_ast::helpers::'+name+'$',s)];assert len(z)==1,(name,z);addr=z[0].split()[0];result=sp.check_output(['addr2line','-i','-e',binary,addr]).decode();rows[name]={'symbol':z[0].split(' ',2)[-1],'address':addr,'source':[(line.split('/checkout/',1)[-1] if '/checkout/'in line else ('<other>/'+line.rsplit('/',1)[-1])) for line in result.splitlines()],'raw_addr2line_sha256':dig(result.encode())}
 return rows

def aggregate():
 gate=read(Y/'terminal.json'); phases=gate['phases']; dct={}
 for ph in phases:
  d=Y/'receipts'/ph; x=read(d/'processes.json');js=x['jobs'];a=read(d/'artifacts.json');p=read(d/'programs.json');rawlinks=[z for z in x['native'] if z['name']=='ld.bfd'];unknown=[z for z in x['native'] if z['name']in ('wild','rust-lld','ld.lld')];assert not unknown,unknown; dct[ph]={'artifacts':len(a),'fresh':sum(z['fresh']for z in a),'pure_lib_full':[v['name']for v in js if v['kind']=='full' and v['crate_types']in (['lib'],['rlib'])],'mixed_full':[v['name']for v in js if v['kind']=='full' and 'cdylib'in v['crate_types']],'binaries_full':[v['name']for v in js if v['kind']=='full' and v['crate_types']==['bin']],'proc_macros_full':[v['name']for v in js if v['kind']=='full' and 'proc-macro'in v['crate_types']],'all_full':sum(v['kind']=='full'for v in js),'link_only':[v['name']for v in js if v['kind']=='link-only'],'stock_wilds':[Path(z['output']).name if z['output'] else None for z in rawlinks],'programs':p,'direct_receipts':{n:sha(d/n)for n in ('artifacts.json','processes.json','inputs.json','programs.json','complete.json','exit.json','stdout.jsonl','stderr')}}
 selected={'ruff_python_ast','ruff_python_parser','ty_vendored','ruff_ranged_value','ruff_python_literal','ruff_linter'};edges=[('settle-current','warm-reverse'),('warm-reverse','unchanged-reverse'),('unchanged-reverse','clean-reverse'),('unchanged-reverse','restored'),('settle-current','unchanged-restored')];df={a+'__'+b:delta(a,b,selected if n==0 else set()) for n,(a,b)in enumerate(edges)};endpoint='settle-current__warm-reverse'; arrows=df[endpoint]; computed={}
 for name,fields in [('raw_archive',['archive']),('standalone_metadata',['rmeta']),('both',['archive','rmeta'])]:computed[name]=[r['name'] for r in arrows if all(r[f][0]!=r[f][1] for f in fields)]
 # Do not presume correctness from reordering sections or discriminating only cached public hash.
 result={'release':{'version':'1.99.0-18','cargo':RELEASE_CARGO,'rustc':sha(SDK/'bin/rustc'),'driver':sha(next((SDK/'lib').glob('librustc_driver-*.so')))},'source':{'commit':H,'parent':OLD,'patch_sha256':sha(Y/'change.patch')},'phases':dct,'local_libraries':df,'edited_changed':computed,'source_locations':{p:symbols(p)for p in ('settle-current','warm-reverse','clean-reverse','restored')},'stale_parser_controls':read(Y/'stale-control/results.json')};write(Y/'result.json',result)
if __name__=='__main__':
 while not (Y/'stale-control/results.json').exists():time.sleep(4)
 aggregate()
