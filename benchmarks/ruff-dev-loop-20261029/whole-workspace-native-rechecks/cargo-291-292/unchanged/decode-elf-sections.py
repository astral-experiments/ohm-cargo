#!/usr/bin/env python3
"""Compare all genuinely different complete ELF bodies, retaining sections and loadable segments for review."""
from pathlib import Path
import argparse,collections,gzip,hashlib,io,itertools,json,os,shutil,struct,subprocess,tempfile
def h(b):return hashlib.sha256(b).hexdigest()
def get(p):
 raw=subprocess.check_output(['zstd','-dcq','--',p]);assert h(raw)==p.name[:-4]
 assert raw[:6]==b'\x7fELF\x02\x01';fields=struct.unpack_from('<16sHHIQQQIHHHHHH',raw,0)
 phoff=fields[5];shoff=fields[6];phent,numph,shent,numsh,shidx=fields[9:]
 assert phent==56 and shent==64 and numsh>0
 sect=[struct.unpack_from('<IIQQQQIIQQ',raw,shoff+i*64) for i in range(numsh)];hdr=sect[shidx];names=raw[hdr[4]:hdr[4]+hdr[5]]
 sections={};listed=[]
 for i,s in enumerate(sect):
  n=names[s[0]:].split(b'\0',1)[0].decode();key=n if n not in sections else n+'#'+str(i);off,size=s[4:6];data=raw[off:off+size] if s[1]!=8 else b''
  sections[key]={'alloc':bool(s[2]&2),'execute':bool(s[2]&4),'file_off':off,'size':size,'type':s[1],'flags':s[2],'addr':s[3],'align':s[-2],'sha256':h(data)};listed.append((key,sections[key]))
 note=sections.get('.note.gnu.build-id');segs=[]
 for i in range(numph):
  ph=struct.unpack_from('<IIQQQQQQ',raw,phoff+i*56);pt,flags,off,addr,phys,n,mem,align=ph;loaded=bytearray(raw[off:off+n])
  if note:
   lo,hi=max(off,note['file_off']),min(off+n,note['file_off']+note['size'])
   if lo<hi:loaded[lo-off:hi-off]=b'\0'*(hi-lo)
  segs.append({'index':i,'type':pt,'flags':flags,'offset':off,'addr':addr,'paddr':phys,'bytes':n,'mem_size':mem,'align':align,'raw_bytes':h(raw[off:off+n]),'mask_only_buildid':h(loaded)})
 return {'size':len(raw),'program_header_table':h(raw[phoff:phoff+phent*numph]),'section_header_table':h(raw[shoff:shoff+shent*numsh]),'sections':sections,'segments':segs}
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('root',type=Path);a.add_argument('observations',type=Path);a.add_argument('out',type=Path);q=a.parse_args()
 payload=json.load(gzip.open(q.observations));roles=collections.defaultdict(dict)
 for arm,phases in payload['arms'].items():
  for phase,r in phases.items():
   for k,v in r['targets'].items():
    d=roles[k].setdefault(v['sha256'],{});d[arm+'/'+phase]=q.root/'state'/arm/'objects'/(v['sha256']+'.zst')
 descriptions={};cases={}
 for k,hashes in sorted(roles.items()):
  if len(hashes)<2:continue
  for code,files in hashes.items():
   if code not in descriptions:descriptions[code]=get(next(iter(files.values())))
  differences={}
  for x,y in itertools.combinations(sorted(hashes),2):
   a,b=descriptions[x],descriptions[y];allsec=sorted(a['sections'].keys()|b['sections'].keys());ds=[c for c in allsec if a['sections'].get(c)!=b['sections'].get(c)];allocated=[c for c in allsec if (a['sections'].get(c,{}).get('alloc') or b['sections'].get(c,{}).get('alloc')) and a['sections'].get(c,{}).get('sha256')!=b['sections'].get(c,{}).get('sha256')]
   mask=lambda s:[(p['bytes'],p['mem_size'],p['addr'],p['flags'],p['mask_only_buildid']) for p in s['segments'] if p['type']==1]
   differences[x+' '+y]={'differing_sections':ds,'allocated_unequal_payloads':allocated,'text_equal':'.text' not in allocated,'rodata_equal':'.rodata' not in allocated,'all_PT_LOAD_equal_masking_only_build_id':mask(a)==mask(b),'program_headers_equal':a['program_header_table']==b['program_header_table'],'section_headers_equal':a['section_header_table']==b['section_header_table']}
  cases[k]={'bodies':{code:sorted(files.keys()) for code,files in hashes.items()},'comparisons':differences}
 o={'targets':len(roles),'different_full_elf_targets':len(cases),'cases':cases,'sections':descriptions}
 with q.out.open('xb') as f,gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0) as z:z.write(json.dumps(o,sort_keys=True,separators=(',',':')).encode()+b'\n')
 print(json.dumps({'all_targets':len(roles),'different':sorted(cases),'compressed_sha256':h(q.out.read_bytes())}))
if __name__=='__main__':main()
