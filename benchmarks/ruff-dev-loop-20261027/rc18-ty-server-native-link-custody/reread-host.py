import ast
import hashlib
import json
import os
from pathlib import Path
import re
import socket
D=Path('/mnt/devbox-scratch/dev-user/ohm-ty-server-e2e-search-control-20261028-v2');P=D.parent/'ohm-combined-prs-20261028';V=P/'whole-wild-width-v2';R=D/'result.json';assert socket.gethostname()=='charlie-ohm-c5-check-1025' and os.sched_getaffinity(0)=={24,25,26,27}
rd=lambda p:json.loads(p.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
j=rd(R);out=[]
assert rd(D/'donor-before.json')==rd(D/'donor-after.json')
for p in j['phases']:
 d=D/p['phase'];assert rd(d/'digest.json')==p and h(d/'exec')==p['overall_trace_sha256'] and h(d/'stderr')==p['stderr_sha256']; rows=[]
 for l in (d/'exec').read_bytes().splitlines():
  if not l.endswith(b'= 0') or b'execve("'not in l:continue
  m=re.search(rb'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[\da-fA-F]+|NULL)',l); assert m
  exe=ast.literal_eval(m[1].decode()); av=ast.literal_eval(m[2].decode());kind=Path(exe).name
  if kind=='ld.bfd': assert '/wild-ld/'in exe and h(Path(exe))==j['stock_wild'] and sha(l)==p['stock_wild_exec_sha256']
  rows.append({'kind':kind,'argv_length':len(av),'event_sha256':sha(l),'input_rlink':any(a.endswith('/'+j['name']+'.rlink') for a in av),'log_sha256':sha(json.dumps(av,sort_keys=True,separators=(',',':')).encode())})
 assert sum(v['kind']=='ld.bfd' for v in rows)==1 and sum(v['kind']=='rustc'and v['input_rlink'] for v in rows)==1
 if 'elf_sha256'in p: assert h(d/'e2e')==p['elf_sha256'] and (d/'e2e').stat().st_size==p['elf_bytes'] and h(d/'list')==p['list_sha256']; assert (d/'list').read_bytes().count(b': test\n')==p['listed_tests']
 else:
  errors=[json.loads(l)for l in (d/'stderr').read_bytes().splitlines()]; primary=[z for z in errors if z.get('level')=='error' and 'linking with' in z['message']]; assert len(primary)==1
  diagnostics=[child['message'] for child in primary[0]['children'] if 'INVALID_LINK_SCRIPT_FOR_E2E_NEGATIVE' in child['message']]; assert len(diagnostics)==1
  snippets=[line.strip() for line in diagnostics[0].splitlines() if 'INVALID_LINK_SCRIPT_FOR_E2E_NEGATIVE'in line]; assert snippets
  diagnostic=[re.sub(r'/[^ ]+',lambda m: Path(m[0]).name,line) for line in snippets]; assert all(len(x)<500 for x in diagnostic),diagnostic
 out.append({'phase':p['phase'],'successful_execve':rows,'raw_exec_summary_sha256':p['overall_trace_sha256'],**({'error_excerpt':diagnostic} if 'elf_sha256'not in p else {})})
cap=P.parent/'ohm-ty-server-e2e-native-capture-20261028-v1';c=rd(cap/'public.json'); assert h(cap/'acquired/replay.json')==c['replay_spec_sha256'] and h(cap/'acquired/argv.bin')==c['raw_argv'] and h(cap/'acquired/env.bin')==c['environment_sha256'] and h(cap/'acquired/cwd.bin')==c['cwd_sha256']; assert all(h(cap/'acquired'/name)==v[0] for name,v in c['temporary_operands'].items()); assert len((cap/'acquired/env.bin').read_bytes().split(b'\0'))-1==c['environment_count']; assert h(cap/'out'/j['name'])==c['e2e_elf'];print(json.dumps({'proof':out,'donor_original_and_final_raw':h(D/'donor-before.json'),'complete_result_json':h(R),'capture_receipt_json':h(cap/'public.json'),'cargo_receipt_version':5,'cpu_mask':sorted(os.sched_getaffinity(0))},sort_keys=True,indent=2))
