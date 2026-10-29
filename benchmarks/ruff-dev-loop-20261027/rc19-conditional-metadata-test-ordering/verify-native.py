"""Verify the per-process Linux syscall order and compiler/fingerprint outcomes."""
import argparse,collections,hashlib,json,re
from pathlib import Path
def sha(x):return hashlib.sha256(x.read_bytes()).hexdigest()
def single(rows):
 assert len(rows)==1,len(rows)
 return rows[0]
def calls(path):
 pending={};out=[]
 for idx,line in enumerate(path.read_text(errors='strict').splitlines(),1):
  m=re.match(r'^(\d+)\s+(\d+\.\d+) (.*)$',line)
  if not m:continue
  pid=int(m[1]);s=m[3]
  if s.startswith('<... ') and ' resumed>' in s:
   if pid not in pending:continue
   start,text=pending.pop(pid);s=text+s.split(' resumed>',1)[1];out.append((pid,start,idx,s))
  elif s.endswith('<unfinished ...>'):
   pending[pid]=(idx,s[:s.index('<unfinished ...>')].rstrip())
  elif re.match('[a-z_0-9]+\\(',s):out.append((pid,idx,idx,s))
 return sorted(out,key=lambda x:x[1])
def exec_map(cmd,matcher):
 result={}
 for pid,i,j,s in cmd:
  m=re.match(r'execve\("([^"]+)",',s);crate=re.search(r'"--crate-name", "(dep|app|middle)"',s)
  if m and crate and matcher(Path(m[1])) and s.endswith('= 0'):result[crate[1]]=pid
 return result
def run(root,expected_cases=10):
 root=root.resolve()
 cases={p.parent.name:json.loads(p.read_text()) for p in root.glob('*/verified.json') if p.is_file()}
 assert len(cases)==expected_cases
 result={}
 for label,case in sorted(cases.items()):
  which=case['which'];scenario=case['scenario'];fixed=which.startswith('proposed')
  producer='middle' if scenario=='direct-middle' else 'dep';consumer='middle' if scenario.startswith('transitive') else 'app'
  marker='middle-metadata' if producer=='middle' else 'dependency-metadata';expected=consumer.replace('app','parent')+'-started'
  observed_marker=('middle-started-early' if consumer=='middle' else 'parent-started-before-middle-finish' if producer=='middle' else 'parent-started-early')
  stats={};raw={}
  for name in ['seed','edited','recovery','unchanged']:
   d=root/label/name;r=json.loads((d/'result.json').read_text());t=d/'kernel.trace';rows=calls(t)
   rust=exec_map(rows,lambda x:x.name=='rustc' and x.parent.name=='bin')
   wrapper=exec_map(rows,lambda x:x.name==which+'-wrapper')
   assert set(rust)==set(wrapper)==set(r['invocations']),(label,name,rust,wrapper,r)
   assert r['exit']==(101 if name=='edited' and scenario=='failure' else 0)
   assert len(r['public_hashes'])==(0 if name=='edited' and scenario=='failure' else 1)
   assert(name!='unchanged' or not rust)
   assert all(v>=n for v,n in zip(r['floor_free'],[45*2**30,40*2**30]))
   raw[name]={f:sha(d/f) for f in ['kernel.trace','stderr','stdout','result.json']}
   stats[name]={'cargo_exit':r['exit'],'real_rustc':sorted(rust),'dependency_hash':next((v['sha'] for v in r['public_hashes'].values()),None)}
   if name=='edited':
    assert producer in rust and consumer in rust
    assert r['markers']['qa-notification-delivered'] and r['markers']['qa-consumer-observed']
    assert not r['markers']['qa-handshake-timeout'] and not r['markers']['parent-timed-out'] and r['markers'][observed_marker]==fixed
    a,b=wrapper[producer],wrapper[consumer]
    def event(pid,predicate):
     return single([(i,j,s) for who,i,j,s in rows if (pid is None or who==pid) and predicate(s)])
    def create(pid,fn):
     return event(pid,lambda s:s.startswith('openat(') and ('/'+fn+'",' in s or '"'+fn+'",' in s) and 'O_CREAT' in s and re.search(r'= [0-9]+$',s))
    # Reconstruct the actual real-rustc artifact, forwarded wrapper stderr bytes,
    # and actor identity. Use completed syscalls for every cross-process boundary.
    ck=event(None,lambda s:s.startswith('write(2,') and ('/lib'+producer+'-') in s and '.rmeta' in s and r'\"artifact\"' in s and r'}\n"' in s and ' = ' in s)
    wn=event(a,lambda s:s.startswith('write(2,') and '.rmeta' in s and r'\"artifact\"' in s and ' = ' in s)
    hashnotice=event(a,lambda s:s.startswith('write(2,') and 'public_api_hash' in s)
    wc=event(a,lambda s:s.startswith('write(2,') and r'\"}}\n' in s and s.endswith('= 4'))
    mc=create(a,marker);mr=event(b,lambda s:s.startswith(('statx(','newfstatat(')) and ('/'+marker+'",') in s)
    assert (mr[2].endswith('= 0') and 'stx_size=5' in mr[2]) if fixed else ('= -1 ENOENT' in mr[2])
    go=create(None,'qa-notification-delivered');confirmed=create(None,'qa-consumer-observed');finished=create(b,expected)
    assert ck[1]<=wn[1]<hashnotice[1]<wc[1]<mr[0]<=mr[1]<finished[0] and wc[1]<go[0] and finished[1]<confirmed[1],(label,ck,wn,hashnotice,wc,mr,go,finished,confirmed)
    if fixed:assert mc[1]<wn[0] and mr[1]<create(b,observed_marker)[0]
    else:assert confirmed[1]<mc[0]
    if scenario=='failure':assert create(a,'dependency-failed')[0]>finished[1] and not r['markers']['dependency-finished']
    if scenario.startswith('transitive'):
     assert r['markers']['middle-finished'] and r['markers']['parent-started'] and not r['markers']['parent-started-before-middle-finish'] and not r['markers']['parent-started-early']
    stats[name]['sequence']=sorted([[x[1],title] for x,title in [(ck,'real-rustc-rmeta'),(mc,'producer-marker-created'),(wc,'metadata-notification-forwarded'),(go,'bounded-wait-open'),(mr,'dependent-marker-present' if fixed else 'dependent-marker-ENOENT'),(finished,'dependent-start-recorded'),(confirmed,'bounded-wait-closed')]])
  if scenario=='failure':
   assert stats['seed']['dependency_hash']!=stats['recovery']['dependency_hash']==stats['unchanged']['dependency_hash'] and stats['recovery']['real_rustc']==['app','dep']
  result[label]={'variant':which,'scenario':scenario,'observations':stats,'raw_sha256':raw}
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--output',type=Path);p.add_argument('--cases',type=int,choices=[2,10],default=10);args=p.parse_args()
 result=run(args.raw,args.cases)
 if args.output:args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
 print('verified',len(result),'fixture histories,',sum(len(v['observations']) for v in result.values()),'physical Cargo commands')
