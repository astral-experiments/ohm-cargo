"""Join each complete retained-object copy to its physical hardlink and its successful promotion."""
import collections
import errno
import gzip
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from sys import argv

base=Path(argv[1]);out=Path(argv[2]);assert not out.exists() and shutil.disk_usage(base).free>48*2**30
def read(f):return json.loads(f.read_bytes())
def sha(f):
 with f.open('rb')as body:return hashlib.file_digest(body,'sha256').hexdigest()
def checksum(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def normalized(p):
 m=re.fullmatch(r'(.+)\.([a-z0-9]{7})(\.rcgu\.o)',p)
 assert m,p
 return m[1]+m[3],m[2]
phases={}; details={}; all_names=[]; asserts=[]; native={}
for arm in ('W','E'):
 logs=base/'states'/f'ruff-{arm}'/'logs'; terminal=read(logs/'terminal.json')
 assert terminal['subject']==arm and terminal['independent_raw_equality']=={'old':True,'new':True}
 names=terminal['inventory'];assert len(set(names))==len(names)==130;all_names.append(names)
 phases[arm]={}; native[arm]={}
 for name,row in terminal['rows'].items():
  r=logs/name; p=read(r/'phase.json');n=read(r/'native.json'); assert sha(r/'phase.json')==row['sha256']
  archive=r/'complete-native-traces.json.gz'; raw_payload=gzip.decompress(archive.read_bytes()); assert n['raw_sha256']==hashlib.sha256(raw_payload).hexdigest()
  bypath={}; positive={};renamed=set();bad=[]
  raw=json.loads(raw_payload); del raw_payload
  for pid,ss in raw.items():
   for line in ss.splitlines():
    if '.rlink-objects/'not in line:continue
    result=re.search(r'\)\s+= (-?\d+)',line)
    if not result:continue
    v=int(result[1])
    if v<0:continue
    qq=re.findall(r'"([^"]+)"',line)
    if line.startswith('linkat('):
     # Both arguments may be absolute, or AT_FDCWD + two quoted arguments.
     if len(qq)!=2:continue
     x,y=qq
     if '/incremental/'in x and '.rlink-objects/'in y and y.endswith('.o'):
      k=y.split('/view/work/',1)[1];kind='restored'
     elif '.rlink-objects/'in x and '/incremental/'in y and x.endswith('.o'):
      k=x.split('/view/work/',1)[1];kind='new'
     else:continue
     assert v==0 and (k not in bypath or bypath[k]==kind), (name,k,bypath.get(k),kind)
     bypath[k]=kind
    elif line.startswith('copy_file_range(')or line.startswith('sendfile('):
     z=re.findall(r'<(/[^>]+)>',line)
     if len(z)<2:continue
     x,y=map(Path,z[:2])
     if not(x.parent==y.parent and x.name.endswith('.o')and x.parent.name.endswith('.rlink-objects')and y.name.startswith('.tmp')):continue
     k=(pid,str(x).split('/view/work/',1)[1],str(y).split('/view/work/',1)[1]); positive.setdefault(k,[]).append(v)
    elif line.startswith(('rename(','renameat(','renameat2(')):
     if len(qq)!=2:continue
     x,y=map(Path,qq)
     if x.parent==y.parent and x.name.startswith('.tmp')and y.name.endswith('.o') and x.parent.name.endswith('.rlink-objects'):
      key=(pid,str(y).split('/view/work/',1)[1],str(x).split('/view/work/',1)[1]);assert key not in renamed;renamed.add(key)
  assert set(positive)==renamed
  geometry={k:{x['path']:x for x in p[k]if x['path'].endswith('.rcgu.o')} for k in ('pre','post')}
  gpre,gpost=geometry.values()
  amounts=collections.Counter();working=[]
  for key,ns in positive.items():
   pid,src,temp=key
   assert src in bypath and src in gpost and ns[-1]==0 and all(x>0 for x in ns[:-1]) and len(ns)>1
   assert sum(ns)==gpost[src]['bytes'] and gpost[src]['links']==1
   amounts[bypath[src]]+=sum(ns)
   working.append([bypath[src],src,temp,pid,sum(ns)])
  assert sum(map(sum,positive.values()))==row['copy_bytes'] and len(positive)==row['copy_count']
  if arm=='E':
   assert {k[1] for k in positive}==set(bypath)
  else:
   assert not positive and not renamed
  prekeys={normalized(k)[0]:v for k,v in gpre.items()};postkeys={normalized(k)[0]:v for k,v in gpost.items()}
  assert len(prekeys)==len(gpre)and len(postkeys)==len(gpost)
  overlap=set(prekeys)&set(postkeys)
  nonce=lambda m: sorted({normalized(n)[1] for n in m})
  before={'count':len(gpre),'nlink1':sum(v['links']==1 for v in gpre.values()),'nonce':nonce(gpre)}
  after={'count':len(gpost),'nlink1':sum(v['links']==1 for v in gpost.values()),'nonce':nonce(gpost)}
  phases[arm][name]={'status':row['status'],'full_rustc':row['full'],'rustc_roster':p['crates'],'link_only':row['link_only'],'stock_wild':row['wild'],'tests':row['native_test_exits'],'ELF':row['elf'],'count_by_link_direction':dict(collections.Counter(bypath.values())),'copied_bytes_by_link_direction':dict(amounts),'copied_files':len(positive),'actual_publish_renames':len(renamed),'preexisting_complete_same_path':len(gpre.keys()&gpost.keys()),'same_logical_CGU_ignoring_nonce':len(overlap),'same_size_logical_CGU':sum(prekeys[k]['bytes']==postkeys[k]['bytes'] for k in overlap),'pre':before,'post':after,'native_full_trace_sha256':n['raw_sha256'],'compressed_trace_sha256':sha(archive),'phase_sha256':sha(r/'phase.json'),'physical_classification_digest':checksum(sorted(working))}
  if arm=='E'and name.startswith('unchanged'):
   selected_keys={normalized(k)[0]for k in bypath}; assert len(selected_keys)==256 and selected_keys<=overlap and not (gpre.keys()&gpost.keys()) and before['nlink1']==len(gpre) and after['nlink1']==len(gpost) and before['nonce']!=after['nonce'];phases[arm][name]['matched_selected_prestat']=len(selected_keys);phases[arm][name]['matched_selected_presize']=sum(prekeys[k]['bytes']==postkeys[k]['bytes']for k in selected_keys);phases[arm][name]['additional_saved_objects_outside_detach']=len(overlap-selected_keys)
 assert set(terminal['rows'])=={'cold-original','historical-edit','unchanged-original','unchanged-edit','invalid','repair','independent-empty-edited','restore-original'}
 native[arm]=sha(logs/'terminal.json')
assert all_names[0]==all_names[1]
for k in phases['W']:
 a,b=phases['W'][k],phases['E'][k]
 assert tuple(a[x] for x in ('status','ELF','tests','stock_wild','count_by_link_direction'))==tuple(b[x] for x in ('status','ELF','tests','stock_wild','count_by_link_direction'))
body={'roles':{'W':'ad005f99d0b51fd62b5c237bc13b31b371a1686e','E':'05efba7a06f5bb71d1efb4b86805800f8b810779'},'terminals':native,'registry_and_sources_sha256':sha(base/'native-binding.json'),'protocol':sha(base/'registered.json'),'test_inventory_size':len(all_names[0]),'test_inventory_commitment':checksum(all_names[0]),'phases':phases,'stock_reflink_probe':read(base/'reflink-capability-v1.json'),'reflink_probe_sha256':sha(base/'reflink-capability-v1.json'),'individual_object_content_note':'Original pre/post geometry has dev, inode, nlink, length and exact path. It has no pre-command per-object content hash. Complete consumer ELFs and all actual copied lengths were authenticated independently.'}
out.write_text(json.dumps(body,indent=2,sort_keys=True)+'\n')
print(sha(out));print(json.dumps({k:[v['count_by_link_direction'],v['copied_bytes_by_link_direction'],v['preexisting_complete_same_path'],v['same_size_logical_CGU'],v['pre']['nonce'],v['post']['nonce']]for k,v in phases['E'].items()}))
