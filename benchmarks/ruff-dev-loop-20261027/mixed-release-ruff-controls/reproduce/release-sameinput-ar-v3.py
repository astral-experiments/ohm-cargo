"""Compare retained vs new member payloads and symbol associations, then force the same full link twice."""
from pathlib import Path
import hashlib,json,os,struct,subprocess as sp,sys
h=Path('/home/dev-user/.cache/ohm-mixed-release-pilot-20261027');s={};exec((h/'release-ruff.py').read_text().split("if sys.argv[1]=='init':")[0],s)
d=s['d'];fn=s['one'];sha=s['sha'];write=s['write'];assert (h/'ordinary.rc').read_text().strip()=='0'
out=h/'same-input-archives-v3';out.mkdir(); labels=['edit2','forced-same-input-0'];arms=['pair','forced']
def fol(arm,tag):return h/'evidence'/arm/tag
def lib(arm,tag,cr):
 key=cr;r=fol(arm,tag)
 for line in (r/'stdout').read_bytes().splitlines():
  a=json.loads(line)
  if a.get('reason')=='compiler-artifact' and a['target']['name']==key:
   p,=map(Path,[x for x in a['filenames'] if x.endswith('.rlib')]);return h/arm/'target'/p.relative_to(d/'target')
 raise RuntimeError(key)
def sec(elf,which):
 assert elf[:6]==b'\x7fELF\x02\x01';off=struct.unpack_from('<Q',elf,40)[0];stride,count,names=struct.unpack_from('<HHH',elf,58)
 slots=[struct.unpack_from('<IIQQQQIIQQ',elf,off+i*stride) for i in range(count)];m=slots[names];txt=elf[m[4]:m[4]+m[5]]
 found=[(slot,elf[slot[4]:slot[4]+slot[5]]) for slot in slots if txt[slot[0]:].split(b'\0',1)[0].decode()==which];assert len(found)==1
 return found[0][1]
def rmeta_link_names(encoded):
 i=0
 def usize():
  nonlocal i
  result=0;shift=0
  while True:
   n=encoded[i];i+=1;result|=(n&127)<<shift
   if n<128:return result
   shift+=7;assert shift<64
 v=[]
 for _ in range(usize()):
  n=usize();v.append(encoded[i:i+n].decode());i+=n;assert encoded[i]==193;i+=1
 return v,encoded[i:]
def inspect(arm,tag,cr):
 rl=lib(arm,tag,cr);members=sp.check_output(['ar','t',rl],text=True).splitlines();assert len(members)==len(set(members))
 contents=[sp.check_output(['ar','p',rl,n]) for n in members];ld=contents[members.index('lib.rmeta-link')]
 listed,tail=rmeta_link_names(sec(ld,'.rmeta-link')); assert listed==[m for m in members if m.endswith('.o')];assert tail.endswith(b'rust-end-file')
 # GNU nm decodes the linker-visible symbol index, including the selected archive member for duplicate symbols.
 lines=sp.check_output(['nm','-s','--defined-only','--no-demangle',rl],text=True,stderr=sp.DEVNULL).splitlines()
 a=lines.index('Archive index:')+1;index=[]
 for line in lines[a:]:
  if not line:break
  n,sep,m=line.rpartition(' in ');assert sep and m in members,(cr,line)
  index.append([n,members.index(m)])
 assert index
 return {'outer_sha':sha(rl),'ordinary':hashlib.sha256(contents[members.index('lib.rmeta')]).hexdigest(),'cgus':[[n,hashlib.sha256(x).hexdigest()] for n,x in zip(members,contents) if n.endswith('.o')],'link_metadata_member':hashlib.sha256(ld).hexdigest(),'remaining_after_exhaustive_filename_decode':tail.hex(),'symbol_index_entries':len(index),'symbol_to_member_ordinal':hashlib.sha256(json.dumps(index,separators=(',',':')).encode()).hexdigest(),'encoded_member_roster_exact':True}
cs=('ruff_wasm','ty_wasm');comp={k:{} for k in cs};last='forced-same-input-0';gold=json.loads((fol('forced',last)/'result.json').read_bytes())
for cr in cs:
 for arm,label in zip(arms,labels):comp[cr][arm]=inspect(arm,label,cr)
for cr in cs:comp[cr]['forced-same-input-0']=inspect('forced','forced-same-input-0',cr)
for op in [1]:
 tag='forced-same-input-'+str(op);stash=out/(str(op)+'-previous');stash.mkdir()
 for cr in cs:
  row=next(j for line in (fol('forced',last)/'stdout').read_bytes().splitlines() if (j:=json.loads(line)).get('reason')=='compiler-artifact' and j['target']['name']==cr)
  raw,=map(Path,[q for q in row['filenames'] if q.endswith('.rmeta')])
  md=h/'forced/target'/raw.relative_to(d/'target')
  so=md.with_suffix('.so');assert so.is_file();so.rename(stash/so.name)
  receipt=md.with_suffix('.rlink-cache.json')
  if receipt.is_file():receipt.rename(stash/receipt.name)
 v=fn('forced','edited',tag);assert sorted((n,kind) for _,n,kind in v['procs'])==sorted((c,'full') for c in cs),v['procs']
 fresh=fn('forced','edited',tag+'-fresh');assert not fresh['procs']
 for cr in cs:
  comp[cr][tag]=inspect('forced',tag,cr);arts=v['artifacts'][cr][0][1];base=gold['artifacts'][cr][0][1];assert all(arts[k]==base[k] for k in ('.rmeta','.so','symbols','embedded'))
 last=tag
write(out/'archives.json',comp);answers={}
for cr,cl in comp.items():
 keys=['ordinary','remaining_after_exhaustive_filename_decode','symbol_index_entries','symbol_to_member_ordinal','encoded_member_roster_exact']
 base=cl['pair'];outc={}
 for name,b in cl.items():
  assert all(base[k]==b[k] for k in keys),(cr,name)
  assert [x[1] for x in base['cgus']]==[x[1] for x in b['cgus']]
  outc[name]={'cgus':len(b['cgus']),'equal_cgu_bytes':True,'different_member_names_from_pair':sum(x[0]!=y[0] for x,y in zip(base['cgus'],b['cgus'])),'symbol_count': b['symbol_index_entries'],'equal_symbol_to_member_index':True,'decoded_name_roster_matches':b['encoded_member_roster_exact'],'remaining_link_metadata_bytes':b['remaining_after_exhaustive_filename_decode']}
 a,b=cl['forced-same-input-0'],cl['forced-same-input-1'];fullnames=sum(x[0]!=y[0] for x,y in zip(a['cgus'],b['cgus']));assert fullnames==len(a['cgus'])
 answers[cr]={'observations':outc,'different_names_between_two_new_full_compiles':fullnames};print(cr,len(a['cgus']),a['symbol_index_entries'],a['remaining_after_exhaustive_filename_decode'],fullnames,flush=True)
write(out/'comparison.json',answers)
