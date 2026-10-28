"""Repeat the actual initial observer checksum capture with the exact three release Cargo images."""
from pathlib import Path
import json,os,shutil,signal,subprocess as sp,sys,time,hashlib
D=Path('/dev/shm/ohm-observer-protocol-h1-20261027'); P=D/'optional-native-pilot1-20261028'; X=P/'pinned-native-controls-v1'; R=P/'pinned-subjects'
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
armed={'A-common':('A','N-common','ignored'),'N-common':('N','N-common','optional'),'Q-common':('Q','N-common','probe'),'N-legacy':('N','N-old-raw','legacy')}
def canon(p):return json.loads(p.read_bytes())
def run_inside(key):
 arm,prior,expected=armed[key]; sdk=P/prior/'active-sdk'; dep=D/'input/equal-length-matrix.py'; fixture=(P/'incidental-archive.py').read_text()
 goal=R/arm/'cargo'; assert sha(goal)==sha(sdk/'bin/cargo')==canon(R/'shared-generation.json')['matched'][arm]['binary']
 rel=D/'release-unicode/rc17-fixed' if key=='N-legacy' else P/'common-release'; rd=canon(rel/'receipt.json')
 assert sha(sdk/'bin/rustc')==rd['frontend']=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
 assert sha(sdk/'lib'/rd['driver_name'])==rd['candidate_postbolt']
 assert rd['candidate_postbolt']==('52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955' if key=='N-legacy' else 'ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99')
 assert sp.check_output([sdk/'bin/rustc','--print=sysroot'],text=True).rstrip()==str(sdk)
 os.environ.update(PRIVATE_NATIVE_SDK=str(sdk),QUALIFIED_CARGO=str(goal),QUALIFIED_RELEASE=str(rel),EXPECT_CAPTURE=expected)
 helpers=dep.read_text().split('cases={}')[0];a=helpers.index("logical=root/'active-sdk'");b=helpers.index('def sha(path):',a)
 helpers=helpers[:a]+"""logical=Path(os.environ['PRIVATE_NATIVE_SDK']);rustup=root/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(logical);receipt=json.loads((release/'receipt.json').read_bytes());installed='fixed'
""" +helpers[b:]
 root=X/key;sys.argv=[str(dep),str(root),'--cargo','fixed','--rust','fixed']
 # One fully independent state per invocation, physical already-verified compiler SDK.
 scope={'__file__':str(dep)};exec(compile(helpers+'\n'+fixture[fixture.index("assert o.rust=="):],'<exact native observer guard>', 'exec'),scope)
 row=canon(root/'result.json');assert row['cargo']==sha(goal) and row['driver']==rd['candidate_postbolt']
if len(sys.argv)>1 and sys.argv[1]=='inside':
 run_inside(sys.argv[2]);sys.exit()
X.mkdir();(X/'space.json').write_text(json.dumps({'before':shutil.disk_usage(P).free,'floor':3*2**30})+'\n')
for key,(arm,prior,expected) in armed.items():
 sdk=P/prior/'active-sdk';assert shutil.disk_usage(P).free>3*2**30+70_000_000
 cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--ro-bind','/dev/shm','/dev/shm','--bind',str(X),str(X),'--tmpfs','/tmp','--ro-bind',str(R/arm/'cargo'),str(sdk/'bin/cargo'),'--','taskset','-c','0-3','python3','-B',__file__,'inside',key]
 with (X/(key+'.log')).open('wb') as out:
  proc=sp.Popen(cmd,stdout=out,stderr=sp.STDOUT,start_new_session=True)
  while proc.poll() is None:
   if shutil.disk_usage(P).free<3*2**30:os.killpg(proc.pid,signal.SIGTERM);proc.wait();raise RuntimeError(('3GiB floor',key))
   time.sleep(.15)
 assert proc.returncode==0,(key,(X/(key+'.log')).read_text()[-2200:])
 print(key,'ok',flush=True)
v={k:canon(X/k/'result.json') for k in armed}
for k,z in v.items():
 z['rows']={phase:{x:y for x,y in r.items() if x in ('value','complete','fresh','all_fresh','units','elf','real','stamps','dep_sha','fp_sha','version','wire','native')}|{'caller_full_compiles':len(r['compiler_exec']),'queries':len(r['capability_queries'])} for phase,r in z['rows'].items()}
(X/'receipt.json').write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
print('verified',sha(X/'receipt.json'), 'free',shutil.disk_usage(X).free,flush=True)
