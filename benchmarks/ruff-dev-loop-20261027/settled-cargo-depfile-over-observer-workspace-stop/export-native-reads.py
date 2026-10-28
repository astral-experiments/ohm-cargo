from pathlib import Path
import gzip,hashlib,json,os,re,subprocess,tarfile,tempfile,sys
H=Path('/home/dev-user/.cache/ohm-output-paths-over261-20261028');Q=H/'union-native-v3'
pub=Path('/tmp')/('over261-union-export-'+str(os.getpid()));pub.mkdir()
h=lambda b:hashlib.sha256(b).hexdigest()
binding={}
def cp(rel,key=None):
 src=H/rel;raw=src.read_bytes();out=(pub/(key or rel));out.parent.mkdir(parents=True,exist_ok=True)
 cleaned=re.sub(rb'socket-firewall-registry[.][A-Za-z0-9_.-]+-[a-f0-9]{16}',b'registry-fixture-hash',raw);assert b'socket-firewall-registry' not in cleaned
 t=out.with_name(out.name+'.gz');t.write_bytes(gzip.compress(cleaned,mtime=0));binding[str(out.relative_to(pub))]=[h(raw),h(cleaned)]
for f in ('union-plan.json','union-qualification.log','union-qualification.rc','offline-key-families.json','rejected-union-v2.json','rejected-ancestor-v1.json','union-native-v3/union.json','union-native-v3/primed.json'):
 if (H/f).is_file():cp(f)
dirs=list(Q.glob('prime-*'))+list(Q.glob('verify-*'))
for d in sorted(dirs):
 for n in ('record.json','observed.json','before.json','after.json','stdout','stderr'):
  if (d/n).is_file():cp(str((d/n).relative_to(H)))
 # Successful proof renames and exact magic/checksum-key bytes represent all replacements.
 subset=[]
 for f in sorted(d.glob('trace.*')):
  with f.open(errors='strict') as handle:
   for line in handle:
    if not any(x+'/' in line for x in ('.ohm-registry-json-v2','.ohm-git-index-sha1dc-v1')):continue
    if not re.search(r'\)\s+=\s+\d',line):continue
    if line.startswith(('rename','link','unlink','truncate','ftruncate','openat')) or (line.startswith('write(') and re.search(r', (21|32)\)\s+=\s+(21|32)\s*$',line)):
     if '/.ohm-registry-json-v2/' in line or '/.ohm-git-index-sha1dc-v1/' in line:subset.append([f.name,line.rstrip()])
 boundary=pub/d.name;boundary.mkdir();(boundary/'proof-syscalls.json.gz').write_bytes(gzip.compress((json.dumps(subset,separators=(',',':'))+'\n').encode(),mtime=0))
outcomes=dict(original_reject_not_modified=(H/'qualified-261-workspace/workspace/qual/trace-parent/record.json').exists(),trust_parent=(H/'trusted-ancestor-v2/normal-parent/record.json').exists(),trust_candidate_exists=(H/'trusted-ancestor-v2/normal-candidate/record.json').exists(),terminal=(Q/'terminal.json').exists(),grants={n:(H/n).exists() for n in ['scoring.grant','trust.scoring.grant','union.scoring.grant']},recorded_slots={path:len(list((H/path).glob('*/ir/*/record.json'))) for path in ('qualified-261-workspace','qualified-261-workspace-trusted','qualified-261-workspace-union')},workspace_source=h((H/'ready.json').read_bytes()),filesystem={str(x):{'total':os.statvfs(x).f_blocks*os.statvfs(x).f_frsize,'available':os.statvfs(x).f_bavail*os.statvfs(x).f_frsize} for x in (H,Path('/mnt/devbox-scratch/dev-user'))})
(pub/'raw-to-portable.json').write_text(json.dumps(binding,sort_keys=True,indent=2)+'\n');(pub/'zero.json').write_text(json.dumps(outcomes,sort_keys=True,indent=2)+'\n')
with tarfile.open(mode='w|gz',fileobj=sys.stdout.buffer) as f:
 for item in sorted(pub.rglob('*')):
  if item.is_file():f.add(item,arcname=str(item.relative_to(pub)),recursive=False)
