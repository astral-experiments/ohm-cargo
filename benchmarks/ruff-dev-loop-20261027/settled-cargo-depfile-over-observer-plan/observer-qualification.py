"""Upgrade isolated copies of three actual falsely fresh -17 observers through two #261 Cargo arms."""
from pathlib import Path
import fcntl,hashlib,json,os,re,shutil,subprocess
import prepare as p
H=p.H;A=H/'adversarial';R=H/'port-migration';arms=('parent','candidate');cases=('tracked-file','include-str','include-bytes');j=lambda f:json.loads(f.read_bytes());stock=p.F/'release17/sdk/bin/cargo';live=p.sdk/'bin/cargo';exp=j(H/'qualified-pair.json');
def switch(file):
 tmp=live.with_name('atomic-private-cargo');shutil.copy2(file,tmp);os.replace(tmp,live);assert p.sha(live)==p.sha(file)
def execute(statedir,arm,case):
 active=A/(case+'-active');assert not active.exists();result=R/arm/case;result.mkdir(parents=True);subprocess.run(['cp','-a','--reflink=auto',statedir,active],check=True);assert (statedir/'private-input.txt').stat().st_ino!=(active/'private-input.txt').stat().st_ino;ref=j(statedir/'report.json');ref0=ref['rows']['again'];e=dict(HOME=str(active),PATH='/home/dev-user/.cargo/bin:/usr/local/bin:/usr/bin:/bin',RUSTUP_HOME=str(active/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(active/'cargo'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='4',OHM_SYNC_DIR=str(active),OHM_SYNC_CONSTANT='fixed',LC_ALL='C.UTF-8',LANG='C.UTF-8',CARGO_TARGET_DIR=str(active/'warm/target'),CARGO_BUILD_BUILD_DIR=str(active/'warm/shared'));source=active/'src';elf=active/'warm/target/debug/hold_direct';public=elf.with_suffix('.d')
 def proof():
  q,=[f for t in ['warm/target','warm/shared'] for f in (active/t).rglob('dep-bin-hold_direct')];raw=q.read_bytes();assert raw[-41:-37]==b'OBS1' and raw[5]==4;return q,raw
 def native():
  o=subprocess.check_output([elf],env=e,cwd=source);n,=re.findall(rb'^sample=(\d+)$',o,re.M);assert b'revision=2' in o.splitlines();return int(n),o
 before=proof()[1];assert before[-33]==1 and p.sha(elf)==ref0['exe'] and native()[0]==17;assert p.sha(statedir/'private-input.txt')==p.sha(active/'private-input.txt')==ref['after']['sha256'];assert active.joinpath('private-input.txt').stat().st_mtime_ns==ref['before']['mtime']==ref['after']['mtime'];assert (pubold:=public.read_bytes()) and b'ohm-foreign-span-bytes' not in pubold;(result/'sealed-before.obs1').write_bytes(before);(result/'sealed-before.d').write_bytes(pubold)
 states={}
 for phase in ['upgrade','again','recreate','corrupt','recovered']:
  d=result/phase;d.mkdir()
  if phase=='recreate':public.rename(d/'retained-before.d')
  if phase=='corrupt':
   q,raw=proof();q.write_bytes(raw[:-1]+bytes([raw[-1]^1]));(d/'tampered.obs1').write_bytes(q.read_bytes())
  cmd=['strace','-f','-qq','-s','65535','-e','trace=execve','-o',str(d/'exec'),'/home/dev-user/.cargo/bin/cargo','+ohm','build','--offline','-p','hold_direct','--message-format=json'];q=subprocess.run(cmd,env=e,cwd=source,capture_output=True,timeout=120);(d/'cargo.jsonl').write_bytes(q.stdout);(d/'stderr').write_bytes(q.stderr);assert q.returncode==0,(d,q.stderr[-900:]);records=[v for row in q.stdout.splitlines() if (v:=json.loads(row)).get('reason')=='compiler-artifact'];dirty=[v['target']['name'] for v in records if not v['fresh']];assert len(records)==4 and dirty==['hold_direct'],(d,[(v['target']['name'],v['fresh']) for v in records]);raw=proof()[1];qref,=[f for t in ['warm/target','warm/shared'] for f in (active/t).rglob('hold_direct*.d') if f.parent.name=='out' and b'ohm-foreign-span-bytes' in f.read_bytes()];pd=public.read_bytes();assert raw[-33]==0 and b'ohm-foreign-span-bytes' in pd and str(active/'private-input.txt').encode() in pd,(d,pd,raw[-41:]);value,out=native();assert value==29;(d/'public.d').write_bytes(pd);(d/'encoded.obs1').write_bytes(raw);(d/'rustc.d').write_bytes(qref.read_bytes());(d/'program').write_bytes(out);trace=(d/'exec').read_text();calls=[l for l in trace.splitlines() if 'execve(' in l and l.rsplit('=',1)[-1].strip()=='0' and ', "--crate-name",' in l];assert any('"hold_direct"' in line for line in calls) and not any('"hold_shapes"' in line or '"hold_probe"' in line for line in calls);states[phase]=dict(dirty=dirty,units=len(records),value=value,complete=raw[-33],sentinel=True,public=p.sha(d/'public.d'),rustc=p.sha(d/'rustc.d'),program=p.sha(d/'program'),encoded=p.sha(d/'encoded.obs1'),phase=phase,source=p.sha(source/'hold_direct/src/main.rs'),input=p.sha(active/'private-input.txt'));p.store(d/'row.json',states[phase]);
 active.rename(R/arm/(case+'-saved-state'));return states

def run():
 os.umask(0o077);os.sched_setaffinity(0,range(8));R.mkdir();v={};assert j(H/'native-ready.json')['stock']==p.sha(stock)
 try:
  for arm in arms:
   bin=H/'subjects'/arm/'cargo';assert p.sha(bin)==exp[arm]['cargo'];switch(bin)
   for case in cases:
    v[arm+'/'+case]=execute(A/(case+'-stock'),arm,case);p.store(R/'progress.json',v);print('native',arm,case,flush=True)
  for case in cases:
   a=v['parent/'+case];c=v['candidate/'+case];assert a==c,(case,{n:{k:(x,c[n][k]) for k,x in row.items() if c[n][k]!=x} for n,row in a.items()})
  p.store(R/'complete.json',v)
 finally:switch(stock)
if __name__=='__main__':
 with p.lock.open('a') as f:fcntl.flock(f,fcntl.LOCK_EX);run()
