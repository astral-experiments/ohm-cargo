"""Profile the official Cargo, preserving the ordinary command's 182 fully fresh artifacts."""
import hashlib, json, os, pathlib, subprocess, time, statistics
H=pathlib.Path.home()
B=H/".cache/ohm-ty-vendored-watch-20261028-v1"; P=H/".cache/ohm-ty-vendored-script-consumer-20261028-v1"/"warm"
O=H/".cache/ohm-ruff-18-fresh-prep-linkscout-20261028"
SDK=H/".cache/ohm-ron-producer-freshness-20261028/official-sdk"; V=O/"tools"
D=pathlib.Path(__file__).resolve().parent
def sha(p):
 with p.open('rb')as fp:return hashlib.file_digest(fp,'sha256').hexdigest()
S=json.loads((O/'status.json').read_text()); assert S['terminal'];want=S['commands'][-1]['products']
ns=['bwrap','--die-with-parent','--tmpfs','/','--dir','/.cargo','--ro-bind','/.cargo/config.toml','/.cargo/config.toml','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--ro-bind','/etc','/etc','--ro-bind','/sys','/sys','--dir','/home','--ro-bind',str(H),str(H),'--ro-bind','/mnt','/mnt','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(P/'checkout'),str(B/'checkout'),'--bind',str(D),str(D)]
for n in ('target','shared','home'):ns+=['--bind',str(O/n),str(B/n)]
ns+=['--chdir',str(B/'checkout'),'--','taskset','-c','0-7']
env={k:v for k,v in os.environ.items()if not k.startswith(('CARGO_','RUSTC_','RUSTUP_')) and k not in ['RUSTFLAGS','RUSTDOCFLAGS','RUSTC','RUSTDOC','CARGO_LOG']}
env.update(RUSTUP_HOME=str(SDK.parent/'official-installer-state/rustup'),CARGO_HOME=str(B/'home'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='8',CARGO_BUILD_BUILD_DIR=str(B/'shared'),CARGO_TARGET_DIR=str(B/'target'),GIT_OPTIONAL_LOCKS='0')
ownership=subprocess.check_output([*ns,"/usr/bin/stat","-c","%n %u %a","/","/home",str(H),str(B/"home")],text=True);print("private-namespace",ownership,flush=True);assert all(row.split()[-2] in ("0","1000") for row in ownership.splitlines())
args=[str(H/'.cargo/bin/cargo'),'+ohm','build','--locked','--offline','-p','ty_vendored']
subprocess.run(['cc','-shared','-fPIC','-O2',D/'align.c','-ldl','-o',D/'align.so'],check=True)
plan=json.loads((D/'plan.json').read_bytes());assert plan['source_sha256']==sha(D/'align.c')
assert os.getloadavg()[0]<2.5
sizes={1:1787150,2:554093,3:5577690}
result={'cargo':sha(SDK/'bin/cargo'),'hook':sha(D/'align.so'),'plan':sha(D/'plan.json'),'products':{pathlib.Path(k).suffix:v for k,v in want.items()},'observations':[]}
def run(arm,label,json_mode=False):
 d=D/label;d.mkdir();pr=d/'hook.log';ee={**env,'LD_PRELOAD':str(D/'align.so'),'OHM_STREAM_PROBE':str(pr),'OHM_STREAM_MODE':arm};argv=[*args,*(['--message-format=json']if json_mode else [])]
 with (d/'stdout').open('wb')as out,(d/'stderr').open('wb')as err:
  start=time.perf_counter_ns();cp=subprocess.run([*ns,*argv],env=ee,stdout=out,stderr=err);elapsed=time.perf_counter_ns()-start
 row={'arm':arm,'label':label,'rc':cp.returncode,'elapsed_ns':elapsed,'streams':[],'stdout':sha(d/'stdout'),'stderr':sha(d/'stderr')}
 for l in pr.read_text().splitlines():
  i,prior,issued,later,requests,readbytes,nsdur=map(int,l.split());row['streams'].append({'id':i,'request':prior,'issued':issued,'later':later,'requests':requests,'bytes':readbytes,'ns':nsdur})
 (d/'receipt.json').write_text(json.dumps(row,sort_keys=True))
 assert cp.returncode==0 and 'Compiling ' not in (d/'stderr').read_text() and len(row['streams'])==6, (row,(d/'stderr').read_text()[:300])
 assert [(s['id'],s['request'])for s in row['streams']]==[(1,16384),(2,16384),(1,65536),(2,65536),(3,16384),(3,65536)]
 for s in row['streams']:
  exp=16384-(plan['offsets'][s['id']-1]%16384) if arm=='B' and s['request']==16384 else s['request']
  assert s['issued']==exp and s['later']==s['request']and s['bytes']==sizes[s['id']]
 if json_mode:
  a=[r for r in map(json.loads,(d/'stdout').read_bytes().splitlines())if r['reason']=='compiler-artifact']; assert len(a)==182 and all(q['fresh']for q in a);row['json_fresh']=len(a)
 assert all(sha(O/'target'/pathlib.Path(k).relative_to(B/'target'))==v for k,v in want.items())
 return row
for arm in 'AB':
 result['observations'].append(run(arm,'gate'+arm,True))
(D/'gates.json').write_text(json.dumps(result,sort_keys=True));print('admitted',sha(D/'gates.json'),flush=True)
for i,order in enumerate(plan['orders']):
 for j,arm in enumerate(order):
  row=run(arm,f'p{i:02}-{j}-{arm}');result['observations'].append(row)
(D/'observations.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
for phase in ('first','second','whole'):
 def val(r): return r['elapsed_ns'] if phase=='whole'else sum(s['ns']for s in r['streams']if s['request']==(16384 if phase=='first'else 65536))
 a=[];b=[]
 for i in range(24):
  pair={r['arm']:r for r in result['observations'][2+2*i:4+2*i]};a.append(val(pair['A']));b.append(val(pair['B']))
 delta=[b-a for a,b in zip(a,b)];print(phase,'A',statistics.median(a),'B',statistics.median(b),'delta',statistics.median(delta),'wins',sum(x<0 for x in delta),flush=True)
