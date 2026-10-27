"""Create a bounded set of public-safe receipts without raw system traces or environment values."""
from pathlib import Path
from collections import Counter
import hashlib,json,os,re,sys
P=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');root=P/'results/cold-ron-v1';ex=P/'results/ron-first-public-v1-pathkeys';ex.mkdir(exist_ok=False);allr={}
def sha(q):
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for a in ['tiny-default','tiny-trusted','whole-default','whole-trusted']:
 phases={};last={}
 for ph in ('cold','unchanged-1','unchanged-2'):
  d=root/a/ph;js=json.loads((d/'summary.json').read_bytes());procs=json.loads((d/'processes.json').read_bytes());native=json.loads((d/'raw-native.json').read_bytes());argv=json.loads((d/'ron-argv.json').read_bytes());rn=d/'ron';fp=next(rn.glob('lib-ron.json'));fpo=json.loads(fp.read_bytes());changed=[{'name':Path(p).name,'before':last[p],'after':h} for p,h in native.items() if last and last[p]!=h];last=native
  reason=[];er=(d/'stderr').read_text();ls=er.splitlines()
  for i,s in enumerate(ls):
   if 'fingerprint dirty for ron v0.12.0' in s:
    line=ls[i+1].split('dirty: ',1)[-1];path=re.search(r'path: "([^"]+)"',line);reason.append({'kind':line.split(' {')[0], 'basename':Path(path[1]).name if path else None,'parent':Path(path[1]).parent.name if path else None})
  expected={'rustc_jobs':{m:sorted(cr for _,cr,mm,*_ in procs['rustc'] if mm==m) for m in ['full','link-only']},'bundled_wild_outputs':sorted(name for _,name,b,_ in procs['native_links'] if b),'other_linker_output_count':sum(not x[2] for x in procs['native_links']),'fresh':js['fresh'],'units':js['units'],'elapsed_ns':js['elapsed_ns'],'test_executables':js['executables'],'native':{str(Path(n).relative_to(P)):h for n,h in native.items()},'changed_native':changed,'cargo_dirty':js['dirty'],'ron':{'physical':len(argv),'all_rustc_argv_sha256':sha(d/'ron-argv.json'),'flags':[v for r in argv for v in r['args'] if v in ['-Zbinary-dep-depinfo','-Zchecksum-hash-algorithm=blake3','-Zohm-observer-dep-info']],'checksum_records':js['depinfo_checksum_count'],'markers':js['depinfo_markers'],'files':js['ron_files'],'fingerprint_json_sha256':sha(fp),'dirty_reasons':reason},'messages_sha256':js['messages'],'actual_successful_cargo_json':sha(d/'stdout'),'stderr_log_sha256':sha(d/'stderr'),'unfiltered_physical_processes_sha256':sha(d/'processes.json')}
  assert len(expected['native'])==len(native);phases[ph]=expected
 allr[a]=phases
(ex/'observations.json').write_text(json.dumps(allr,indent=2,sort_keys=True)+'\n')
for a,ss in allr.items():print(a,[(p,len(r['rustc_jobs']['full']),len(r['rustc_jobs']['link-only']),len(r['bundled_wild_outputs']),r['other_linker_output_count'],round(r['elapsed_ns']/1e9,3),len(r['changed_native'])) for p,r in ss.items()],ss['unchanged-1']['ron']['dirty_reasons'])
