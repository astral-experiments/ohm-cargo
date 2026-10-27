"""Analyze existing unscored native traces and preserve only read-only input proofs. Never counts an opened output as a changed input."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,os,re,subprocess,sys,tarfile,time
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';Q=X/'nonparser-whole-inputs-campaign-v1';out=Q/'input-attribution';out.mkdir(mode=0o700,exist_ok=True);W='/home/dev-user/code/oss/ruff-ohm-whole-native-20261027/';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027'); T=P/'native-target';S=P/'shared';commit_ends=('rmeta','rlib','a','so','o');J=lambda f:json.loads(f.read_bytes())
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=1)+'\n')
rf=re.compile(rb'\s=\s(\d+)<([^>]*?)>$');fc=re.compile(rb'(?:clone3?|vfork|fork)\(.*\)\s+=\s+(\d+)$');opnames=(b'open(',b'openat(',b'openat2(')
def get_reads(q):
 p=subprocess.Popen(['zstd','-q','-dc',str(q)],stdout=subprocess.PIPE);ans=defaultdict(set);parents={};types=Counter();read_only_unknown=Counter()
 with tarfile.open(fileobj=p.stdout,mode='r|') as t:
  for f in t:
   if not f.isfile() or not f.name.startswith('exec.'):continue
   pid=int(f.name.rsplit('.',1)[1]);stream=t.extractfile(f);pending=None
   for line in stream:
    s=line.strip()
    if s.endswith(b'<unfinished ...>'):pending=s.removesuffix(b'<unfinished ...>');continue
    if s.startswith(b'<... '):
     cut=s.find(b'resumed>');
     if cut<0 or pending is None:continue
     s=pending+s[cut+8:];pending=None
    m=fc.fullmatch(s)
    if m and int(m[1])>0:parents[int(m[1])]=pid;continue
    if not s.startswith(opnames) or (m:=rf.search(s)) is None:continue
    v=os.fsdecode(m[2]);
    # Only strong positive reads. O_RDWR/O_CREAT, O_PATH and opened output never provide a sole exclusion.
    if re.search(rb'\bO_RDONLY\b',s[:m.start()]) and not re.search(rb'\b(?:O_PATH|O_CREAT|O_TRUNC|O_DIRECTORY)\b',s[:m.start()]):ans[pid].add(v)
    else:read_only_unknown[pid]+=1
 assert p.wait()==0;return ans,parents,read_only_unknown

def analyze(d,prior):
 j=J(d/'receipt.json');mode=j['mode'];old=J(prior/'artifact-state.json');cur=J(d/'artifact-state.json');diff=J(d/'artifact-changes.json');before=J(prior/'setup.json')['source_set'];after=J(d/'setup.json')['source_set'];source_diff={W+r:{'old':before[r],'new':after[r]} for r in before if before[r]!=after[r]};payloads=dict(diff,**source_diff);pcs=J(d/'processes.json');who={r['pid']:r for r in pcs['typed']};orp=pcs['unclassified'];opens,parent,nonread=get_reads(d/'exec-traces.tar.zst');reads=defaultdict(set)
 for pid,ps in opens.items():
  n=pid;seen=set()
  while n not in who and n in parent and n not in seen:seen.add(n);n=parent[n]
  if n in who:reads[n].update(ps)
 fl={};dest=out/mode/d.name;dest.mkdir(parents=True,exist_ok=True);rall=[];c=Counter()
 for pid,r in who.items():
  if r['kind'] not in ('wild','rustc-full','rustc-link-only','rustc-guarded-unknown','other-linker'):continue
  # Exclude paths explicitly output by the process. Cargo aliases are reported separately.
  outs={r['link_output']} if r['link_output'] else set();ext=set(r['externs']);actual=reads[pid];changed_read={p:payloads[p] for p in sorted(actual.intersection(payloads)-outs) if payloads[p]['old']!=payloads[p]['new']};changed_argv={p:payloads[p] for p in sorted(ext.intersection(payloads)-outs) if payloads[p]['old']!=payloads[p]['new']};settled=sorted(set(cur).intersection(old).intersection(actual)-set(diff));
  # Distinguish retained Cargo artifacts from system libs, ephemeral objects, and scripts, never use incomplete sets as an equality certificate.
  unknown_cargo=sorted(p for p in actual if p.startswith(str(P)) and not p.startswith(str(P/'frozen-toolchain')) and p not in cur and p not in source_diff);tmp=sorted(p for p in actual if p.startswith('/tmp/'));obj=sorted(p for p in actual if p.endswith(('.o','.rlib','.a','.so','.ld','.lds')));outpub=r['link_output'] if r['link_output'] in cur else None
  pan=pid;ancestry=[]
  while pan in parent:pan=parent[pan];
  par=r['parent_job']
  while par in who:
   prev=who[par];ancestry.append({'pid':par,'kind':prev['kind'],'crate':prev['crate']});par=prev['parent_job']
  row={'pid':pid,'kind':r['kind'],'crate':r['crate'],'test':r['test'],'link_output':r['link_output'],'ancestors':ancestry,'exec_sha256':r['exec_sha256'],'tool_sha256':r['image_sha256'],'actual_regular_read_candidates':len(actual),'changed_actual_paths':changed_read,'declared_changed_externs':changed_argv,'known_exact_same_cargo_reads':settled,'unknown_logical_native_input_paths':unknown_cargo,'temporary_reads':tmp,'link_object_or_archive_reads':obj,'raw_out_in_roster':{'old':old.get(outpub,{}).get('sha256'),'new':cur[outpub].get('sha256')} if outpub else None,'native_argument_paths':[a for a in r['argv'] if a.startswith(('-l','-L','--script','--sysroot','-plugin','@','-T'))] if r['kind']=='wild' else [],'failed_searches':r['missing'] if r['kind']=='wild' else [],'unparsed_or_error_opens':r['other_open_errors'],'unfinished_open_lines':r['unfinished']};rall.append(row);c[(r['kind'],bool(changed_read))]+=1
 # One child actual native read can reject skipping its ancestor rustc-link-only/full as a whole.
 for r in rall:
  w=[w for w in rall if w['kind']=='wild' and any(a['pid']==r['pid'] for a in w['ancestors'])];r['descendant_wilds']=[w['pid'] for w in w];r['changed_by_actual_child_read']=any(w['changed_actual_paths'] for w in w);r['has_observed_changed_input']=bool(r['changed_actual_paths']) or r['changed_by_actual_child_read']
 save(dest/'jobs.json',rall);save(dest/'summary.json',{'label':d.name,'mode':mode,'whole_rust_and_wild_jobs':len(rall),'counts':{k+':'+str(v):n for (k,v),n in c.items()},'after_including_native_child':dict(Counter(r['kind']+':'+str(r['has_observed_changed_input']) for r in rall)),'unclassified_execs':orp,'unknown_no_witness':[{'kind':r['kind'],'crate':r['crate'],'pid':r['pid'],'reads':r['actual_regular_read_candidates'],'output':r['link_output']} for r in rall if not r['has_observed_changed_input']],'read_evidence':'O_RDONLY regular non-output positive opens, exact logical path with full-byte before/after hashes; always inherit descendant native positive. Missing, opened outputs, arguments alone, unretained temporaries and file names alone never certify a whole skip.'});print(mode,d.name,json.dumps(J(dest/'summary.json')['after_including_native_child']),flush=True)
for mode in ('build','test'):
 dirs=sorted((Q/'receipts'/mode).glob('*/receipt.json'),key=lambda p:p.stat().st_mtime_ns);prev=None
 for f in dirs:
  d=f.parent;j=J(f)
  if j['phase'] in ('edit','restore') and prev and not (out/mode/d.name/'summary.json').is_file():analyze(d,prev)
  prev=d
