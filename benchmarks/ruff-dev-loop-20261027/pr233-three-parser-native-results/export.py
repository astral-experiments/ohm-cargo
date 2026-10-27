"""Export bounded typed native evidence from the completed unscored H5 comparison of Rust #232 and #233."""
from pathlib import Path
import collections,hashlib,json,shutil,tarfile,re
base=Path.home()/'.cache/ohm-233-position-qualified-20261027'
out=base/'first-occurrence-classic-pr233-h5-v2'; w=base/'pr233-three-parser-protocol-h5-v2'
complete=out/'complete.json';assert complete.is_file() and not (out/'failure.txt').exists()
pub=base/'pr233-three-edit-native-results-h5-v2';assert not pub.exists();pub.mkdir()
def read(p):return json.loads(p.read_bytes())
def dump(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def h(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
for rel in ('complete.json','test-admission.json','preflight.json'):
 shutil.copy2(out/rel,pub/rel)
shutil.copy2(w/'source-rehearsal.json',pub/'source-rehearsal.json')
shutil.copy2(w/'novel-plan.json',pub/'preregistered-plan.json')
shutil.copy2((Path(__file__).with_name('classic-verify.py') if Path(__file__).with_name('classic-verify.py').exists() else Path(__file__).with_name('verify.py')),pub/'verify.py')
dump(pub/'subject-provenance.json',{'binding_sha256':h(w/'binding.json'),'plan_sha256':h(w/'novel-plan.json'),'plan_url':read(w/'binding.json')['plan_url'],'arms':read(w/'binding.json')['arms'],'host':read(w/'binding.json')['host']['host_tools']})
import sys
sys.path.insert(0,str(w))
from h5paths import release_output_roster
allrows=[]
for mode in (['build','test'] if read(complete)['test_admitted'] else ['build']):
 for name in (mode+'-observations.json',mode+'-complete.json'):
  shutil.copy2(out/name,pub/name)
 cold={}
 for arm in 'BC':
  c=out/'receipts'/mode/arm
  for cmd in sorted(c.iterdir()):
   src=cmd/'receipt.json'
   if not src.is_file():continue
   r=read(src);p=r['product'];t=r['processes'];ids={}
   for row in t['jobs']:
    fn=row['pid'];ids.setdefault(fn,{'process_trace_sha256':h(cmd/fn),'roles':[]})['roles'].append([row['crate'],row['kind']])
   for key,vals in t['native'].items():
    for fn in vals:ids.setdefault(fn,{'process_trace_sha256':h(cmd/fn),'roles':[]})['roles'].append([key])
   proof={'native_process_trace_sha256':ids,'cargo_json_sha256':h(cmd/'stdout'),'complete_private_receipt_sha256':h(src),'physical_jobs':[{'crate':job['crate'],'kind':job['kind'],'file':job['pid'],'recipe_basename':None if not job['recipe'] else Path(job['recipe']).name} for job in t['jobs']], 'native_process_files':t['native'],'compiler_probe_count':len(t['queries']),'recipe_before':r['recipe_before'],'recipe_after':r['recipe_after']}
   oral=read(cmd/'cli.json')
   brief={k:r[k] for k in ('arm','mode','phase','source_view','status','unit_count','fresh_units','elf_count','executable_count','process_totals','native_totals')}
   frozen_roster=release_output_roster((json.loads(line) for line in (cmd/'stdout').read_bytes().splitlines()),arm)
   assert frozen_roster==r['release_output_roster']
   brief.update(release_output_roster=frozen_roster,name=cmd.name,dirty_targets=p['dirty'],roster_sha256=p['structural_roster'],messages_sha256=p['messages'],old_cli=p['diagnostics'],novel_cli=oral,**proof)
   if 'elf' in p:brief['workspace_elf_sha256']={n:{k:e[k] for k in ('raw','size','content_with_two_wild_fields_masked')} for n,e in p['elf'].items()}
   if 'raw_fresh_elf' in r:brief['workspace_elf_sha256']=r['raw_fresh_elf']
   if 'mixed' in p:
    brief['mixed']={}
    for cr,m in p['mixed'].items():
     a=m['archive'];brief['mixed'][cr]={k:m[k] for k in ('rmeta_bytes','rmeta_sha256','private_svh','stable_crate_id','public_svh','embedded_object_sha256','root_listing_sha256','exports','zero_byte_allocations','normalized_archive_sha256')}
     brief['mixed'][cr]['native_archive']={k:a[k] for k in ('sha256','symbol_index_entries','symbol_name_member_ordinal_sha256','objects','rmeta_link')};brief['mixed'][cr]['cdylib_sha256']=m['cdylib_elf']['raw']
   dst=pub/'commands'/mode/arm/(cmd.name+'.json');dst.parent.mkdir(exist_ok=True,parents=True);dump(dst,brief)
   allrows.append({'file':str(dst.relative_to(pub)),**{k:brief[k] for k in ('name','arm','mode','phase','source_view','unit_count','fresh_units','process_totals','native_totals')}})
 header_diffs={}
 for label in read(out/(mode+'-observations.json'))['cross_arm']:
  info=[read(out/'receipts'/mode/arm/label/'receipt.json')['product']['mixed'] for arm in 'BC'];header_diffs[label]={}
  for cr in ('ruff_wasm','ty_wasm'):
   lists=[(out/'retained-mixed'/(x[cr]['rmeta_sha256']+'.root.txt')).read_text().splitlines() for x in info]
   def deps(lines):
    res={}
    for line in lines:
     m=re.match(r'^(\d+) (\S+) hash ([a-f0-9]+) host_hash (\S+) kind (.+)$',line)
     if m:res[m[2]]=[int(m[1]),m[3],m[4],m[5]]
    return res
   left,right=map(deps,lists);header_diffs[label][cr]={'line_counts':list(map(len,lists)),'dependency_count':[len(left),len(right)],'different_imported_entries':{key:[left.get(key),right.get(key)] for key in sorted(left.keys()|right.keys()) if left.get(key)!=right.get(key)},'complete_decoded_sha256':[x[cr]['root_listing_sha256'] for x in info]}
 dump(pub/(mode+'-cross-arm-header-differences.json'),header_diffs)
 within={}
 for arm in 'BC':
  prev='original-baseline'; within[arm]={}
  for case in read(w/'novel-plan.json')['schedule']:
   for direction in ('edit','restore'):
    label=case+'-'+direction; pair=[read(out/'receipts'/mode/arm/n/'receipt.json') for n in (prev,label)]
    a,b=(r['product'] for r in pair)
    assert set(a['elf'])==set(b['elf'])
    mixed={}
    for cr in ('ruff_wasm','ty_wasm'):
     u,v=a['mixed'][cr],b['mixed'][cr]
     mixed[cr]={'raw_rmeta_same':u['rmeta_sha256']==v['rmeta_sha256'],'private_svh_same':u['private_svh']==v['private_svh'],'public_svh_same':u['public_svh']==v['public_svh'],'raw_rlib_same':u['archive']['sha256']==v['archive']['sha256'],'native_cgu_payloads_same':sum(aa[1:]==bb[1:] for aa,bb in zip(u['archive']['objects'],v['archive']['objects'])),'native_cgu_counts':[len(u['archive']['objects']),len(v['archive']['objects'])],'raw_cdylib_same':u['cdylib_elf']['raw']==v['cdylib_elf']['raw']}
    within[arm][label]={'input_state':prev,'output_state':label,'native_elf_count':len(a['elf']),'changed_elf_names':[k for k in sorted(a['elf']) if a['elf'][k]['raw']!=b['elf'][k]['raw']],'mixed':mixed,'changed_signed_cli':pair[0]['novel_cli']!=pair[1]['novel_cli']}
    prev=label
 dump(pub/(mode+'-within-arm-transitions.json'),within)
 br=out/'bridges'/mode
 for p in sorted(br.glob('*/summary.json')):
  dest=pub/'bridges'/mode/p.parent.name;dest.mkdir(parents=True);shutil.copy2(p,dest/'summary.json')
dump(pub/'processes.json',allrows)
import subprocess, sys
shutil.copy2(Path(__file__).with_name('classic-products.py'), pub/'classic-products.py')
shutil.copy2(Path(__file__),pub/'export.py')
subprocess.run([sys.executable,'-B',pub/'classic-products.py',w,out,pub/'linked-products.json'],check=True)
intro='''# Three held-out Ruff edits on Rust #232 and fixed #233

Arm B runs #232. Arm C runs fixed #233. All four initial build stores were physically separate. Both compiler releases used the same Cargo #254 and bundled Wild binaries. Each mode exposed each release to each source change for the first time, after training only on unmodified Ruff. The command records and linker witnesses below cover the complete working tree. No timing endpoint was registered in this cohort.

Each recorded compiler and Wild invocation is bound to its per-process trace hash. The comparison includes every full and link-only Rust job, including its actual parser dependency, each linked product and the raw executable and ELF section digests. The comparisons for .text and .rodata use section payload bytes. The separate masked digest suppresses only the GNU build ID and .rodata section entry size. All remaining bytes count.

The initial runner stopped before any edits because Cargo puts each compiler release in a separate physical output namespace. The new run starts every state from empty. Cross-release unit rosters use a single exact path-component substitution. The extractor independently reapplies it to every raw Cargo artifact message. The per-arm raw scope, complete remaining path and diagnostic identity, and same-release raw file paths stay visible.

The ordinary Rust callers use the same release and dependency store that emitted the input. The build and test stores have 501 and 619 units. The immediate commands must have zero Rust jobs and zero native links. No Cargo test binaries execute. The historical signed-pattern edit changes both pinned Ruff diagnostics on first exposure and restores them on reversal.

Run python3 -B verify.py in this directory. The included export and physical projection scripts can regenerate these records on the prepared H5 host using the complete private native invocation receipts and registered frozen worker.
'''
(pub/'README.md').write_text(intro)
files=sorted(p for p in pub.rglob('*') if p.is_file());(pub/'SHA256SUMS').write_text(''.join(h(p)+'  '+str(p.relative_to(pub))+'\n' for p in files))
archive=pub.with_suffix('.tar.gz')
with tarfile.open(archive,'w:gz',compresslevel=6) as tg:tg.add(pub,arcname=pub.name)
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':h(archive),'included_commands':len(allrows)}))
