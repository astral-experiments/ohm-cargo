"""Select only the three declared generated-file input streams from the two ordinary builds."""
import collections,hashlib,json,pathlib,re
H=pathlib.Path.home();P=H/'.cache/ohm-ruff-18-fresh-prep-linkscout-20261028'; B=H/'.cache/ohm-ty-vendored-watch-20261028-v1'
R=pathlib.Path('target/debug/build/workspaces/5183fbb458952a35/v2-63fe60e05f649687')
byname={n:R/pkg/gen/'out'/n for n,pkg,gen in [('generated.rs','ruff_unicode_names2','f17900a6a44d7d41'),('generated_phf.rs','ruff_unicode_names2','f17900a6a44d7d41'),('zipped_typeshed.zip','ty_vendored','55bc40c417024a68')]}
logical={str(B/p):n for n,p in byname.items()}; result={'files':{},'commands':{}}
for n,rel in byname.items():
 f=P/rel; data=f.read_bytes();result['files'][n]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'dep_info':[]}
for f in (P/'target').rglob('*.d'):
 if not any(t in f.name for t in ('unicode_names','ty_vendored')) or not f.is_file():continue
 data=f.read_bytes()
 for l in data.splitlines():
  m=re.match(rb'^# checksum:([a-z0-9]+)=([a-f0-9]{64}) file_len:(\d+) (.+)$',l)
  if not m or m[4].decode(errors='replace')not in logical:continue
  n=logical[m[4].decode()];row={'filename':f.name,'raw_depfile_sha256':hashlib.sha256(data).hexdigest(),'algorithm':m[1].decode(),'digest':m[2].decode(),'bytes':int(m[3])}
  if row not in result['files'][n]['dep_info']:result['files'][n]['dep_info'].append(row)
for label in ('fs1','fs2'):
 group=[]
 for snap in sorted((P/'logs/ordinary-secured-v1'/label).glob('trace.*')):
  opened={}
  for i,line in enumerate(snap.read_text(errors='surrogateescape').splitlines()):
   if not any(n in line for n in byname):continue
   if line.startswith('openat('):
    m=re.search(r'= (\d+)<([^>]+)>',line)
    if m and (p:=m[2])in logical:
     v={'name':logical[p],'open_line':i+1,'read_calls':[],'source_trace':snap.name};group.append(v);opened[m[1]]=v
   else:
    m=re.match(r'^(?:read|pread64)\((\d+)<([^>]+)>.*?, (\d+)\)\s+= (\d+)',line)
    if m and (p:=m[2])in logical:opened[m[1]]['read_calls'].append([int(m[3]),int(m[4])])
    if line.startswith('close(') and (m:=re.match(r'close\((\d+)<([^>]+)>.*?= 0',line))and m[2]in logical:opened.pop(m[1])['close_line']=i+1
  assert not opened
 for v in group:
  assert v['read_calls'][-1][1]==0 and sum(r for _,r in v['read_calls'])==result['files'][v['name']]['bytes']
  v['requests']=dict(collections.Counter(a for a,b in v.pop('read_calls')))
 assert len(group)==6;result['commands'][label]=group
print(json.dumps(result,sort_keys=True,indent=2))
