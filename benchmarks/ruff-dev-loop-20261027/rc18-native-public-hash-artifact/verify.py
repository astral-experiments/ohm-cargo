"""Recompute all individual file digests and join each compiler transcript to its physical exec."""
from collections import Counter
from pathlib import Path
import hashlib,json,re,tarfile

root=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
subjects={'release17':('7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c','618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7'),'candidate':('4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f','22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f')}
reference={}; summary={}
for tag in ['exact','physical-copy']:
 with tarfile.open(root/(tag+'.tar.gz')) as t:
  d={m.name:t.extractfile(m).read() for m in t.getmembers() if m.isfile()};assert len(d)==len(t.getmembers()) and all(not Path(k).is_absolute() and '..' not in Path(k).parts for k in d)
 assert json.loads(d.pop('PHYSICAL-SHA256.json'))=={k:[len(v),sha(v)] for k,v in d.items()}
 source=d['git-fixture/rmake.rs'];git_files={k:sha(v) for k,v in d.items() if k.startswith('git-fixture/')};binding=json.loads(d['source-receipt.json']);assert sha(source)==binding['source']=='4c0496ffa8e65be21a321e01bf7653c44e4e80ffe2333e5644133c57f0ee73e5'
 if tag=='exact':reference=git_files
 else:
  assert reference==git_files
  old=source.splitlines(); new=d['actual-rmake.rs'].splitlines();assert len(old)==len(new) and [i+1 for i,(a,b) in enumerate(zip(old,new)) if a!=b]==[192]
  assert b'copying preexisting metadata' in old[191] and all(w in new[191] for w in [b'original-metadata.rmeta',b'metadata_work_product()',b'm.dev()',b'm.ino()']);supp=json.loads((root/'physical-build.json').read_bytes());assert sha(d['actual-rmake.rs'])==supp['source']
 for arm,images in subjects.items():
  prefix=arm+'/';load=lambda p:json.loads(d[prefix+p]); stderr=d[prefix+'stderr'];res=load('terminal.json');assert (res['actual_rustc'],res['actual_driver'])==images and res['mode']==tag
  assert sha(stderr)==res['stderr'] and sha(d[prefix+'stdout'])==res['stdout'];assert res['rmake']==(binding['elf'] if tag=='exact' else supp['elf'])
  actual=[]
  for key,b in d.items():
   if not key.startswith(prefix+'exec.'):continue
   for line in b.splitlines():
    m=re.match(rb'execve\("([^"]+)",',line)
    if m and line.endswith(b' = 0'):actual.append(m.group(1).decode())
  n=sum(x.endswith('/rustup/toolchains/ohm/bin/rustc') for x in actual);assert n==res['rustcs'];public=[]
  for i in range(n):
   top=prefix+f'native/{i:03d}';entry=json.loads(d[top+'.json']);assert sha(d[top+'.stdout'])==entry['output'] and sha(d[top+'.stderr'])==entry['errors'];assert entry['argv'][:3]==['/home/dev-user/.cargo/bin/rustc','+ohm','--sysroot'];
   messages=[json.loads(l) for l in d[top+'.stderr'].splitlines() if l.startswith(b'{')];pub=[x['public_api_hash']['value'] for x in messages if x.get('$message_type')=='artifact' and 'public_api_hash' in x];public.append(pub)
  sr={'calls':n,'exit':res['exit']}
  if tag=='exact':
   assert n==2 and res['exit']==101 and b'rmake.rs:192:5:' in stderr and b'the static max level is `info`' in stderr
   o=res['end_metadata_files'];assert len(o)==3 and 'original-metadata.rmeta' in o and 'liblib.rmeta' in o and len({(r['sha256'],r['dev'],r['inode'],r['n']) for r in o.values()})==1
  elif arm=='release17':
   assert n==19 and res['exit']==101 and b'physical-copy.rs:300:5:' in stderr and b'assertion `left != right` failed' in stderr;assert public[17]==public[18]==['284083a4fd74d2c3c892fb7b996cc936'];sr['column-hashes']=public[17:19]
  else:
   assert n==77 and res['exit']==0 and public[17]!=public[18]==public[19] and len(public[17])==len(public[18])==1;sr['column-hashes']=public[17:20];sr['downstream-executions']={Path(x).name:c for x,c in Counter(actual).items() if '/canonical-lab/work/' in x};assert sr['downstream-executions']=={'caller':3,'macro-user':6,'private-macro-user':6,'macro-value-user':6}
  summary[tag+'-'+arm]=sr
print(json.dumps(summary,indent=2,sort_keys=True))
