"""Timed section, including isolated per-arm first-transition validation."""
from pathlib import Path
import json,os,re,shutil,subprocess as sp,sys,time
from mechanics import digest,get,store,sound_timing
from member_archive import witness
def summarise_stderr(payload):
 return [m.group(1).decode()+' '+m.group(2).decode() for l in payload.splitlines() if (m:=re.match(rb'^\s*(Compiling|Checking)\s+(\S+)',l))]
def checked_pair(study,a,sel,st,now,d,cmd,before):
 PH,V,SRC,REP,ROOT=study.PH,study.V,study.SRC,study.REP,study.ROOT
 simple=a[0];trial=PH/sel/st/a;training=REP/sel/st/(simple+'-trained');native=REP/sel/st/(simple+'-probe')
 assert st!=now and simple in 'AB' and a[1:].startswith('-slot') and all(not any((trial/(k+'-upper')).iterdir())for k in ('products','shared'))
 start=get(training/'repeat/result.json');expected=get(native/'first/result.json');rep=get(native/'repeat/result.json');clean=get(REP/sel/now/'A-cold/cold/result.json');clean2=get(REP/sel/now/'B-cold/cold/result.json')
 assert before==start['marker_after']==expected['marker_before'] and all(digest(V/k)==val for k,val in start['artifacts'].items())
 handles=[(d/name).open('xb',buffering=0)for name in ('edit.stdout','edit.stderr','repeat.stdout','repeat.stderr')]
 try:
  edit=sound_timing(cmd,handles[0],handles[1],SRC,study.env);mid=study.amark();repeat=sound_timing(cmd,handles[2],handles[3],SRC,study.env)
 finally:
  for f in handles:f.close()
 assert edit['status']==repeat['status']==0 and mid==study.amark()==expected['marker_after'] and (mid==before)==(simple=='B')
 jobs={};streams={}
 for label,ref in [('edit','first'),('repeat','repeat')]:
  so=(d/(label+'.stdout')).read_bytes();se=(d/(label+'.stderr')).read_bytes()
  kind=summarise_stderr(se);want=summarise_stderr((native/ref/'stderr').read_bytes());assert not so and b'Finished'in se and b'error:'not in se and kind==want,(sel,a,label,kind,want,se[-550:]);jobs[label]=kind;streams[label+'.stdout']=digest(so);streams[label+'.stderr']=digest(se)
 assert jobs['edit'] and not jobs['repeat']
 result={k:digest(V/v)for k,v in expected['targets'].items()};equiv={k:(witness(V/expected['targets'][k])['typed']if k.endswith('.rlib')else val)for k,val in result.items()}
 assert equiv==expected['semantic']==clean['semantic']==clean2['semantic']
 root_set=set(expected['targets'].values())
 held_inputs={k:v for k,v in start['artifacts'].items()if k not in set(start['targets'].values())}
 assert all(digest(V/k)==v for k,v in held_inputs.items()) and all(k in expected['artifacts']and expected['artifacts'][k]==v for k,v in held_inputs.items())
 # Verify the actual measured output with an external process after both clocks.
 cli=study.rust
 def run(what,args):
  z=sp.run(list(map(str,args)),cwd=SRC,env=study.env,capture_output=True,timeout=40);(d/(what+'.stdout')).write_bytes(z.stdout);(d/(what+'.stderr')).write_bytes(z.stderr);return z
 if sel=='check':
  source=V/'lint-witness/bad.rs';assert source.is_file();z=run('valid',[cli,'+ohm','--edition=2024','--emit=metadata','--extern','ruff_text_size='+str(V/expected['targets']['library.rmeta']),V/'consumer.rs','-o',V/'lint-witness/valid.rmeta']);f=run('invalid',[cli,'+ohm','--edition=2024','--emit=metadata','--extern','ruff_text_size='+str(V/expected['targets']['library.rmeta']),source,'-o',V/'lint-witness/bad.rmeta']);assert z.returncode==0 and f.returncode!=0 and b'E0599'in f.stderr;oracle=dict(valid_exit=0,invalid_exit=f.returncode,code='E0599',invalid_stderr=digest(f.stderr),valid_rmeta=digest(V/'lint-witness/valid.rmeta'))
 elif sel=='build':
  dest=V/'lint-caller';z=run('caller-build',[cli,'+ohm','--edition=2024','--extern','ruff_text_size='+str(V/expected['targets']['library.rlib']),V/'consumer.rs','-o',dest]);assert z.returncode==0;f=run('caller',[dest]);assert f.returncode==0 and f.stdout==b'17 29 12\n'and not f.stderr;oracle=dict(caller=digest(dest),value=f.stdout.decode().strip(),exit=0)
 else:
  dest=V/expected['targets']['test'];z=run('list',[dest,'--list']);f=run('tests',[dest,'--test-threads=1']);names=[l[:-6]for l in z.stdout.decode().splitlines()if l.endswith(': test')];assert z.returncode==f.returncode==0 and b'3 passed; 0 failed'in f.stdout;oracle=dict(test_sha=digest(dest),list=names,list_sha=digest(z.stdout),all_passed=3)
 assert oracle==expected['oracle']==clean['oracle']==clean2['oracle']
 return dict(edit=edit,repeat=repeat,streams=streams,jobs=jobs,mid=mid,files=result,semantic=equiv,oracle=oracle,unchanged_other_artifacts=len(held_inputs),expected_first=digest(native/'first/result.json'),independent_clean=[digest(REP/sel/now/(t+'-cold')/'cold/result.json')for t in 'AB'],initial_files=start['artifacts'],removed_instrumentation=True,argv=cmd)
