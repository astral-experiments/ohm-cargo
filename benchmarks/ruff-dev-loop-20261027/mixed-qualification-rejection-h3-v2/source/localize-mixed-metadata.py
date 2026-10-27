"""Relate exact mixed metadata byte offsets to compiler-decoded roots and dependency hashes."""
import argparse,gzip,hashlib,json,re,struct,sys
from collections import Counter
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('record',type=Path);p.add_argument('out',type=Path);a=p.parse_args();r=a.record;output={}; sha=lambda b:hashlib.sha256(b).hexdigest()
def root_info(v):
 f=v['rmeta_sha256'];txt=(r/'rmeta'/(f+'.root.txt')).read_text();t=txt.split('=External Dependencies=');assert len(t)==2;lines=t[1].strip().splitlines();dep={}
 for l in lines:
  m=re.fullmatch(r'(\d+) (\S+) hash ([0-9a-f]{32}) host_hash (.*?) kind (\S+) (\S+)(.*)',l);assert m,l
  dep[m[2]]=dict(ordinal=int(m[1]),svh=m[3],host=m[4],kind=m[5],visibility=m[6],rest=m[7])
 return t[0].splitlines(),dep

def raw_info(v):
 md=v['rmeta_sha256'];c=gzip.decompress((r/'rmeta'/(md+'.gz')).read_bytes());assert sha(c)==md and c[:7]==b'rust\0\0\0' and c[-13:]==b'rust-end-file';return c

def locate(b,h):
 v=bytes.fromhex(h);forms={'literal-be':v,'reverse-all':v[::-1],'reverse-half':v[:8][::-1]+v[8:][::-1],'swapped-half':v[8:]+v[:8]};return {k:[m.start() for m in re.finditer(re.escape(q),b)] for k,q in forms.items() if q in b}

def spans(d):
 runs=[]
 for i in d:
  if runs and runs[-1][1]==i:runs[-1][1]+=1
  else:runs.append([i,i+1])
 return runs
for lft,rgt in [('A-first-edit','gold-A-cold'),('B-first-edit','gold-B-cold'),('C-first-edit','gold-B-cold'),('C-first-edit','forced-C-forced-edit'),('B-first-edit','forced-C-forced-edit'),('B-first-edit','C-first-edit'),('B-cold','C-cold'),('B-cold','A-cold')]:
 key=lft+'__'+rgt;output[key]={}
 L,R=(json.loads((r/'arm-receipts'/(k+'.json')).read_bytes()) for k in [lft,rgt])
 for cr in ['ruff_wasm','ty_wasm']:
  x,y=(i['products'][cr] for i in [L,R]);A,B=map(raw_info,[x,y]);ra,da=root_info(x);rb,db=root_info(y);ds={k:[da.get(k),db.get(k)] for k in sorted(da.keys()|db.keys()) if da.get(k)!=db.get(k)};e=[i['true_mixed_compiler'][cr]['externs'] for i in [L,R]];diff_ex={k:[e[0].get(k),e[1].get(k)] for k in e[0].keys()|e[1].keys() if [q[1] if q else None for q in [e[0].get(k)] ]!=[q[1] if q else None for q in [e[1].get(k)]]};rawdiff=[i for i in range(min(len(A),len(B))) if A[i]!=B[i]];offa,offb=struct.unpack_from('<Q',A,8)[0],struct.unpack_from('<Q',B,8)[0];ranges=spans(rawdiff);hdrh=[i for i in rawdiff if i>=offa];aws=[i for i in rawdiff if i<offa];loc={label:[locate(A,x[label]),locate(B,y[label])] for label in ['private_svh','public_svh']};sd={k:v for k,v in ds.items() if not all(v) or v[0]['svh']!=v[1]['svh']};locations={k:[locate(A,v[0]['svh']) if v[0] else {},locate(B,v[1]['svh']) if v[1] else {}] for k,v in sd.items()};ar=[json.loads(gzip.decompress((r/'native-archive'/(z['raw_rlib_sha256']+'.json.gz')).read_bytes())) for z in [x,y]];ncg=sum(a[1:]!=b[1:] for a,b in zip(ar[0]['objects'],ar[1]['objects']));ident={k:[x[k],y[k]] for k in ['rmeta_sha256','rmeta_bytes','public_svh','private_svh','stable_crate_id','embedded_object_sha256','normalized_archive_sha256','raw_rlib_sha256']};report={'identities':ident,'root':{'before':ra,'after':rb},'dependencies':len(da),'dependency_differences':ds,'dependency_hash_mismatch_count':len(sd),'changed_raw_direct_externs':diff_ex,'root_record_offsets':[offa,offb],'diff_bytes_same_positions':len(rawdiff),'changed_ranges':ranges,'pre_root_diff_bytes':len(aws),'root_or_tail_diff_bytes':len(hdrh),'root_hash_encoded_positions':loc,'dep_hash_encoded_positions':locations,'raw_elf_equal':x['cdylib_elf']['raw']==y['cdylib_elf']['raw'],'all_native_objects_equal':ncg==0 and len(ar[0]['objects'])==len(ar[1]['objects']),'object_count':len(ar[0]['objects']),'num_changed_object_payloads':ncg,'symbol_to_member_ordinal_equal':ar[0]['symbol_name_member_ordinal_sha256']==ar[1]['symbol_name_member_ordinal_sha256'],'c_exports_equal':x['exports']==y['exports']};output[key][cr]=report;print(key,cr,'byte changes',len(rawdiff),len(A),len(B),'root',offa,offb,'fields',[(k,v[0]==v[1]) for k,v in ident.items() if k.endswith('svh')],'dep-metadata',list(sd)[:9],len(sd),'direct-extern',list(diff_ex)[:7],len(diff_ex),'objdiff',ncg,'ELF',report['raw_elf_equal'],'prefix diffs',len(aws),'suffix diffs',len(hdrh))
a.out.write_bytes((json.dumps(output,sort_keys=True,indent=2)+'\n').encode())
