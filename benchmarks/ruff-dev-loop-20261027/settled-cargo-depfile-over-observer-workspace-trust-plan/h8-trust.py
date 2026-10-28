"""Repair the study-owned ancestor after the zero-score qualification and enforce the original native gates."""
import fcntl,hashlib,json,os,re,shutil,stat,subprocess,sys
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-paths-over261-20261028');phase=sys.argv[1];assert phase in ('qualify','score')
P=json.loads((H/'trust-amendment.json').read_bytes())
worker=H/'whole-paths.py';h=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest();reg=lambda p:json.loads(p.read_bytes())
assert h(worker)==P['original_worker'] and h(H/'plan.json')==P['original_plan'] and h(H/'rejected-ancestor-v1.json')==P['rejected_ancestor'] and h(Path(__file__))==P['coordinator']
sys.argv=[str(worker),'h8',phase];source=worker.read_text();end=source.index('os.umask(0o077);os.sched_setaffinity');g={'__file__':str(worker)};exec(compile(source[:end],str(worker),'exec'),g);s=g['s'];q=H/'trusted-ancestor-v2';out=H/'qualified-261-workspace-trusted';g['out']=out
v=reg(H/'rejected-ancestor-v1.json');root_id=v['ancestors'][str(H)]
def save(p,source):p.write_text(json.dumps(source,sort_keys=True,indent=2)+'\n')
def product(bytes=True):
 rr=s.R/'crates/ty_python_semantic/src/types/relation.rs';assert h(rr)==v['source'] and h(Path(v['index_path']))==v['index_sha'] and reg(H/'ready.json')['source_sha']==v['source']
 dp={str(p.relative_to(H/'workspace/target/debug')):h(p) for p in g['depfiles']('workspace')};assert dp==v['public_deps']
 for n,(dig,dev,ino,size,mtime) in v['products'].items():
  p=Path(n);st=p.stat();assert (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)==(dev,ino,size,mtime),n
  if bytes:assert h(p)==dig,n
def old():
 a=H/'qualified-261-workspace';assert not (a/'qualify.json').exists() and not any(a.glob('*/ir/*/record.json')) and h(a/'workspace/qual/trace-parent/record.json')==v['rejected_audit'] and h(a/'workspace/qual/trace-parent/stdout')==v['rejected_stdout']
def direct_switch(file):
 live=g['binary'];tmp=live.with_name('trust-next-cargo');shutil.copy2(file,tmp);os.replace(tmp,live);assert h(live)==h(file)
def hit_probe(arm):
 d=q/('hit-'+arm);d.mkdir();c=['strace','-f','-qq','-s','900','-e','trace=openat','-o',str(d/'opened'),*g['s'].cmds('workspace'), '--message-format=json'];res=subprocess.run(c,cwd=s.cwd('workspace'),env=s.env('workspace'),capture_output=True,check=True);(d/'stdout').write_bytes(res.stdout);(d/'stderr').write_bytes(res.stderr);units=[item for x in res.stdout.splitlines() if (item:=json.loads(x)).get('reason')=='compiler-artifact'];assert len(units)==501 and all(x['fresh'] for x in units);lines=(d/'opened').read_text().splitlines();selected={};completed=[];pending={}
 for line in lines:
  first=re.match(r'^\s*(\d+)\s+(openat\(.*)<unfinished \.\.\.>$',line);last=re.match(r'^\s*(\d+)\s+<\.\.\. openat resumed>(.*)$',line)
  if first:pending[first[1]]=first[2].rstrip()
  elif last and last[1] in pending:completed.append(pending.pop(last[1])+last[2])
  else:completed.append(line)
 for name in ('.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2'):
  # Every accepted row is the Cargo process opening a real numbered proof for a read.
  base=os.fsencode(H/'cargo-home'/name).decode()+'/';paths={m[1] for text in completed if (m:=re.search(r'openat\([^,]+, "([^"]+)", O_RDONLY[^)]*\)\s+=\s+[0-9]+',text)) and m[1].startswith(base) and Path(m[1]).is_file()};assert paths,(name,d)
  selected[name]=sorted(paths)
 save(d/'hit.json',dict(files=selected,stdout=h(d/'stdout'),stderr=h(d/'stderr'),open_trace=h(d/'opened'),spaces=501))
def qualify():
 assert H.is_dir() and not H.is_symlink() and H.stat().st_uid==os.geteuid() and stat.S_IMODE(H.stat().st_mode)==0o775 and H.stat().st_ino==root_id['ino']
 old();product();assert all(not(H/'cargo-home'/s).exists() for s in ('.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2'))
 q.mkdir();assert not (H/'scoring.grant').exists() and not out.exists();os.chmod(H,0o700);assert stat.S_IMODE(H.stat().st_mode)==0o700
 oref=None
 for arm in ('stock','parent','candidate'):
  if arm=='stock':direct_switch(s.prepare.old/'release17/sdk/bin/cargo')
  else:g['switch'](arm)
  ds=g['depfiles']('workspace');pre=g['stamps'](ds);outp=q/('normal-'+arm);r=g['invoke'](outp,'workspace','audit');after=g['stamps'](ds);assert sorted(Path(k).name for k in pre if pre[k]!=after[k])==['libruff_wasm.d','libty_wasm.d']
  assert r['units']==501 and set(r['products'])==set(v['products']);proof=g['proofs']()
  if oref is None:oref=proof
  else:assert proof==oref
  if arm!='stock':hit_probe(arm);assert g['proofs']()==oref
  product()
 save(q/'repaired.json',dict(input_mode='0775',new_mode='0700',rejected=h(H/'rejected-ancestor-v1.json'),original_rust_fingerprint=v['index_sha'],proof=oref,old_untouched=v['rejected_audit']))
 g['main']();assert g['proofs']()==oref;old();product();save(q/'terminal.json',dict(phase=phase,original=h(H/'plan.json'),replacement=h(H/'trust-amendment.json'),anchor=h(out/'workspace/qual/anchor.json'),control=h(out/'qualify.json'),proof=oref))
def score():
 old();assert (H/'trust.scoring.grant').read_text().strip()==h(H/'trust-amendment.json') and (q/'terminal.json').is_file() and stat.S_IMODE(H.stat().st_mode)==0o700
 x=reg(q/'terminal.json');assert g['proofs']()==x['proof'] and h(out/'workspace/qual/anchor.json')==x['anchor'];product();g['main']();assert g['proofs']()==x['proof'];product();old();save(q/'scored.json',dict(phase=phase,original=h(H/'plan.json'),replacement=h(H/'trust-amendment.json'),anchor=x['anchor'],record=h(out/'score.json')))
os.umask(0o077);os.sched_setaffinity(0,range(8))
with s.LOCK.open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);(qualify if phase=='qualify' else score)()
