"""Verify true shared-locked byte reads and the external manifest's two observations."""
from pathlib import Path
import ast,hashlib,json,re,sys
root=Path(sys.argv[1]).resolve()
def sha(data):return hashlib.sha256(data).hexdigest()
def req(test,message):
 if not test:raise ValueError(str(message))
out={};gold=(root/'gold.lock').read_bytes()
stages=json.loads((root/'terminal.json').read_text())['stages'];req(len(stages)==9,stages)
def syscalls(trace):
 pending={};rows=[]
 for i,line in enumerate(trace.read_text().splitlines(),1):
  m=re.fullmatch(r'(\d+)\s+\d+\.\d+ (.*)',line)
  if not m:continue
  pid=int(m[1]);s=m[2]
  if s.endswith('<unfinished ...>'):pending[pid]=(i,s.split('<unfinished ...>')[0].rstrip());continue
  if s.startswith('<... ') and ' resumed>' in s:
   if pid not in pending:continue
   start,begin=pending.pop(pid);s=begin+s.split(' resumed>',1)[1]
  else:start=i
  rows.append((start,i,pid,s))
 return sorted(rows)
for label in stages:
 d=root/label;row=json.loads((d/'row.json').read_text());k=d/'kernel.trace'
 req(row['kernel_sha256']==sha(k.read_bytes()),label)
 req(sha((d/'stderr').read_bytes())==row['stderr_sha256'] and sha((d/'stdout').read_bytes())==row['stdout_sha256'],label)
 if label=='seed':req(row['lock_before'] is None,label)
 else:req(row['lock_before']==row['lock_after'],label)
 rows=syscalls(k);lof=str(root/'ws/Cargo.lock');mk=str(root/'target/.cargo-resolve-cache-v1');late=str(root/'late/Cargo.toml')
 streams=[];current=None;events=[];clocks=[]
 for begin,end,pid,s in rows:
  if s.startswith(('openat(','open(')) and ('"'+lof+'"') in s and 'O_RDONLY' in s and not re.search(r'= -1',s):
   req(current is None,(label,'overlap',s));current={'first':begin,'pid':pid,'data':bytearray(),'locked':False,'eof':False,'unlock':False}
  if current is not None and pid==current['pid'] and ('<'+lof+'>') in s:
   if s.startswith('flock(') and 'LOCK_SH' in s:
    req(s.endswith('= 0'),s);current['locked']=True
   elif s.startswith('read('):
    req(current['locked'] and not current['unlock'],s)
    m=re.search(r', ("(?:[^"\\]|\\.)*"), \d+\) = (\d+)$',s);req(m,(label,s))
    data=ast.literal_eval('b'+m[1]);req(len(data)==int(m[2]),s);current['data'].extend(data)
    if not data:current['eof']=True
   elif s.startswith('flock(') and 'LOCK_UN' in s:
    req(s.endswith('= 0'),s);current['unlock']=True
   elif s.startswith('close('):
    req(current['locked'] and current['eof'] and current['unlock'],(label,current,s));streams.append((current['first'],end,bytes(current['data'])));current=None
  if s.startswith(('openat(','open(')) and ('"'+mk+'"') in s and 'O_RDONLY' in s:
   status='ENOENT' if 'ENOENT' in s else 'open';events.append((begin,end,'marker-'+status,pid))
  if s.startswith(('openat(','open(')) and ('"'+late+'"') in s:
   status='ENOENT' if 'ENOENT' in s else 'open';events.append((begin,end,'late-'+status,pid))
 req(current is None,label)
 diag=row['diagnostic']
 if diag:diag=diag.replace(lof,'Cargo.lock')
 result={'exit':row['exit'],'graph':row.get('edges'),'diagnostic':diag,'lock_reads':[{'line_range':[b,e],'bytes':len(s),'sha256':sha(s)} for b,e,s in streams],
         'opens':[[b,e,role] for b,e,role,pid in events],'kernel_sha256':row['kernel_sha256'],'stderr_sha256':row['stderr_sha256'],'stdout_sha256':row['stdout_sha256']}
 if label.endswith('-appears'):
  req(len(streams)>=2 and streams[0][2]==streams[1][2],label)
  actor=json.loads((d/'actor.json').read_text());req(actor['published'] and actor['lock']==row['lock_before'] and actor['lock'][-1]==sha(streams[0][2]),label)
  r0,r1=streams[:2]
  missing=[b for b,e,role,p in events if role=='late-ENOENT' and r0[0]<b<r0[1]]
  rendez=[b for b,e,role,p in events if role=='marker-open' and r0[0]<b<r0[1]]
  present=[b for b,e,role,p in events if role=='late-open' and r1[0]<b<r1[1]]
  req(len(missing)==len(rendez)==len(present)==1 and missing[0]<rendez[0] and r0[1]<r1[0],(label,events,streams))
  req(actor['manifest_at_release'][-1]==sha((root/'late/Cargo.toml').read_bytes()),label)
  code=(d/'stderr').read_text();version='not-a-version' if label.startswith('semantic') else '0.1.0'
  req(code.count('path dependency now missing late v'+version)==1,label)
  if label.startswith('semantic'):
   req(row['exit']==101 and len(streams)==2 and "unexpected character 'n' while parsing major version number" in diag,label)
  else:req(row['exit']==0 and result['graph']==[['bridge','late'],['member','bridge']],label)
  result['simultaneous_checks']={'first_closed_before_second_opened':True,'reread_identical_lock':True,'missing_then_successful_external_open_inside_respective_shared_locks':True,
                                'manifest_sha256':actor['manifest_at_release'][-1],'receipt_sha256':sha((d/'actor.json').read_bytes())}
 if label=='malformed-first-no-writer':
  req(len(streams)==1 and streams[0][2]==b'version = [\n' and not events and row['exit']==101 and 'TOML parse error at line 1, column 12' in diag,label)
 if label in ['semantic-present-control','malformed-static-control']:
  opposite='semantic-appears' if label[0]=='s' else 'malformed-first-no-writer'
  req(result['diagnostic']==out[opposite]['diagnostic'],label)
 if label in ['recovered','unchanged']:
  req(row['exit']==0 and streams[0][2]==gold and row['edges']==[['bridge','late'],['member','bridge']],label)
 if label=='unchanged':
  req('reusing the cached workspace resolution' in (d/'stderr').read_text() and len(streams)==1,label)
 out[label]=result
result={'image':json.loads((root/'terminal.json').read_text())['image'],'stages':out}
if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('verified nine native Cargo metadata commands;',out['semantic-appears']['lock_reads'][0]['sha256'],'read twice across manifest publication')
