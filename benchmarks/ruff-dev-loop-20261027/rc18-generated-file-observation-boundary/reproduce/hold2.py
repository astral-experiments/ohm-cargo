"""Observe a real content change strictly between the normal Cargo reads of one generated ZIP."""
import hashlib, io, json, os, pathlib, shutil, struct, subprocess, sys, zipfile
H=pathlib.Path.home(); B=H/'.cache/ohm-ty-vendored-watch-20261028-v1'; P=H/'.cache/ohm-ty-vendored-script-consumer-20261028-v1/warm'
O=H/'.cache/ohm-ruff-18-fresh-prep-linkscout-20261028'; SDK=H/'.cache/ohm-ron-producer-freshness-20261028/official-sdk'; W=O/'between-v2';W.mkdir()
def sha(b):return hashlib.sha256(b).hexdigest()
state={}
def log(): (W/'evidence.json').write_text(json.dumps(state,sort_keys=True,indent=2));print(json.dumps(state,sort_keys=True),flush=True)
for n in ('home','shared','target'):subprocess.run(['cp','-a','--reflink=auto',P/n,W/n],check=True)
(W/'source.c').write_bytes(sys.stdin.buffer.read()); hook=W/'hook.so'
subprocess.run(['cc','-shared','-fPIC','-O2',W/'source.c','-ldl','-o',hook],check=True)
zip_path,=list((W/'target').rglob('zipped_typeshed.zip'))
rel=zip_path.relative_to(W); old=zip_path.read_bytes();changed=bytearray(old); z=zipfile.ZipFile(io.BytesIO(old))
eocd=old.rfind(b'PK\x05\x06');cd=struct.unpack_from('<I',old,eocd+16)[0]
assert old[cd:cd+4]==b'PK\x01\x02'
offset=struct.unpack_from('<I',old,cd+42)[0]; assert old[offset:offset+4]==b'PK\x03\x04'
for location in (cd+12,offset+10):changed[location]^=1
assert z.namelist()==zipfile.ZipFile(io.BytesIO(changed)).namelist() and old!=changed
for a in (old,changed):
 zz=zipfile.ZipFile(io.BytesIO(a));stub=zz.read('stdlib/functools.pyi')
 assert sha(stub)=='721696b22e172c4f9dbe15ec5e04a04a9939188eca12d8110ab62f9de81d96a1'
before=zip_path.stat();temp=W/'target/.ohm-held-replacement'; temp.write_bytes(changed)
os.chmod(temp,before.st_mode&0o7777); os.utime(temp,ns=(before.st_atime_ns,before.st_mtime_ns))
assert zip_path.stat().st_size==temp.stat().st_size and zip_path.stat().st_mtime_ns==temp.stat().st_mtime_ns
state.update(zip_old=sha(old),zip_changed=sha(changed),zip_size=len(old),same_mtime=True,differing_bytes=[i for i,(a,b)in enumerate(zip(old,changed)) if a!=b],stub=sha(stub),cargo=sha((SDK/'bin/cargo').read_bytes()),hook=sha(hook.read_bytes()),commands=[])
ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(P/'checkout'),str(B/'checkout'),'--bind',str(W),str(W)]
for n in ('target','shared','home'):ns+=['--bind',str(W/n),str(B/n)]
ns+=['--chdir',str(B/'checkout'),'--','taskset','-c','0-7']
env={k:v for k,v in os.environ.items()if not k.startswith(('CARGO_','RUSTC_','RUSTUP_')) and k not in ['RUSTFLAGS','RUSTDOCFLAGS','RUSTC','RUSTDOC','CARGO_LOG']}
env.update(RUSTUP_HOME=str(SDK.parent/'official-installer-state/rustup'),CARGO_HOME=str(B/'home'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='8',CARGO_BUILD_BUILD_DIR=str(B/'shared'),CARGO_TARGET_DIR=str(B/'target'),GIT_OPTIONAL_LOCKS='0')
args=[str(H/'.cargo/bin/cargo'),'+ohm','build','--locked','--offline','-p','ty_vendored','--message-format=json']
for label,inject,mutate in [('unchanged',True,False),('between',True,True),('holding_changed',False,False),('restored',False,False)]:
 if label=='restored':
  zip_path.write_bytes(old);os.utime(zip_path,ns=(before.st_atime_ns,before.st_mtime_ns))
 subenv=env.copy()
 if inject:subenv.update(LD_PRELOAD=str(hook),CARGO_PREP_WATCHED=str(B/rel),CARGO_PREP_LOG=str(W/(label+'.hook')),CARGO_PREP_REPLACEMENT=str(B/'target/.ohm-held-replacement')if mutate else '')
 with (W/(label+'.out')).open('wb')as out,(W/(label+'.err')).open('wb')as err:
  rc=subprocess.run([*ns,*args],env=subenv,stdout=out,stderr=err).returncode
 arts=[v for v in map(json.loads,(W/(label+'.out')).read_bytes().splitlines())if v['reason']=='compiler-artifact']
 final=next(a for a in arts if a['target']['name']=='ty_vendored'); hist=[]
 for s in final['filenames']:
  p=W/'target'/pathlib.Path(s).relative_to(B/'target');data=p.read_bytes();hist.append({'file':p.suffix,'sha256':sha(data),'old_zip':data.count(old),'changed_zip':data.count(changed)})
 events=(W/(label+'.hook')).read_text().splitlines() if (W/(label+'.hook')).is_file() else []
 state['commands'].append({'label':label,'rc':rc,'artifacts':len(arts),'dirty':[a['target']['name']for a in arts if not a['fresh']],'products':hist,'hook_log':events,'zip':sha(zip_path.read_bytes()),'stdout_sha256':sha((W/(label+'.out')).read_bytes()),'stderr_sha256':sha((W/(label+'.err')).read_bytes())});log()
 assert rc==0 and len(arts)==182
 if inject: assert len(events)>=2 and sum('mutated 1'in e for e in events)==int(mutate)
 if label=='unchanged':assert not state['commands'][-1]['dirty']
 if label=='between':assert 'ty_vendored' in state['commands'][-1]['dirty']
 assert all(p['changed_zip']==(2 if p['file']=='.rlib' else 1)*int(label in ('between','holding_changed')) and p['old_zip']==(2 if p['file']=='.rlib' else 1)*int(label in ('unchanged','restored')) for p in hist)
state['terminal']=True;log()
