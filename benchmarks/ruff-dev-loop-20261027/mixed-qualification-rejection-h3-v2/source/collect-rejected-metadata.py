"""Preserve the exact failed H3 evidence and label the complete full/full and guarded/full controls."""
import collections,gzip,hashlib,json,os,re,shutil,sys,subprocess
from pathlib import Path
x=Path.home()/'.cache/ohm-233-position-qualified-20261027';r=x/'mixed-native-full-abc-h3-v2';g=x/'mixed-native-abc-grants-h3-v2';w=x/'mixed-native-abc-protocol-h3-v2';out=Path(sys.argv[1]);out.mkdir();meta=out/'rmeta';meta.mkdir();archive=out/'native-archive';archive.mkdir();art=out/'arm-receipts';art.mkdir();rd=lambda p:json.loads(p.read_bytes());dump=lambda p,v:p.write_bytes((json.dumps(v,indent=2,sort_keys=True)+'\n').encode());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert (g/'qualify.rc').read_text().strip()=='1' and (r/'failure.txt').is_file() and not any((r/n).exists() for n in ('build.csv','test.csv','statistics.json','preflight-complete.json'));assert not (r/'receipts/test').exists()
summary={};rejected={p.name:p.read_text() for p in r.glob('oracle-mismatch-*.txt')};dump(out/'rejection.json',{'rc':1,'no_scores':True,'no_test_mode':True,'primary_declared_mismatches':rejected,'original_rc_sha':sha(g/'qualify.rc'),'failure_sha':sha(r/'failure.txt'),'binding':sha(w/'runner-binding.json')});shutil.copy2(r/'failure.txt',out/'failure.txt')
selected={k:'/{}'.format(k) for k in []}
for d in sorted((r/'receipts/build').glob('*/*')):
 if not (d/'receipt.json').is_file():continue
 tag,phase=d.parent.name,d.name;z=rd(d/'receipt.json');summary[f'{tag}/{phase}']={'status':z['status'],'units':z['unit_count'],'fresh':z['fresh_units'],'jobs':dict(collections.Counter(j['kind'] for j in z['processes']['jobs'])),'wild':len(z['processes']['native']['wild']),'diagnostics':z['product']['diagnostics'],'receipt':sha(d/'receipt.json')}
 if phase not in ('cold','condition-edit','condition-restore','first-edit','forced-edit','initial-fresh'):continue
 if tag.startswith('gold-') and phase=='initial-fresh':continue
 if tag not in ('gold-A','gold-B') and phase=='initial-fresh':continue
 if 'mixed' not in z['product']:continue
 view={'source':z['state'],'arm':z['arm'],'logical_context':tag,'phase':phase,'receipt':sha(d/'receipt.json'),'products':{},'actual_compiler_jobs':z['processes']['jobs'],'true_mixed_compiler':z['processes']['mixed_inputs'],'manifest_proof':z['manifest_proof'],'full_workload_ELF':{k:[v['raw'],v['content_with_two_wild_fields_masked'],v['gnu_build_id'],v['rodata_entsize']] for k,v in z['product']['elf'].items()}}
 for cr,v in z['product']['mixed'].items():
  md=v['rmeta_sha256'];q=r/'retained-mixed'/(md+'.gz');dmp=r/'retained-mixed'/(md+'.root.txt');assert sha(dmp)==v['root_listing_sha256'] and hashlib.sha256(gzip.decompress(q.read_bytes())).hexdigest()==md
  if not (meta/q.name).exists():shutil.copyfile(q,meta/q.name);shutil.copyfile(dmp,meta/dmp.name)
  u=v['archive'];view['products'][cr]={k:y for k,y in v.items() if k!='archive'};view['products'][cr]['raw_rlib_sha256']=u['sha256'];view['products'][cr]['archive']= {k:f for k,f in u.items() if k!='objects' and k!='rmeta_link'};ref=archive/(u['sha256']+'.json.gz');
  if not ref.exists():ref.write_bytes(gzip.compress(json.dumps(u,sort_keys=True,separators=(',',':')).encode(),mtime=0))
 dump(art/(tag+'-'+phase+'.json'),view)
for place in sorted((r/'bridges').glob('*/*/*/receipt')):
 dest=out/'readers'/place.parent.name;dest.mkdir(parents=True);[shutil.copyfile(p,dest/p.name) for p in place.iterdir() if p.is_file()]
dump(out/'all-completed-commands.json',summary);cl=rd(r/'cloned-artifacts-build.json');dump(out/'cloned-state-proof.json',{'distinct':len(cl),'original':sha(r/'cloned-artifacts-build.json'),'all_different_inodes':all(v['different_inodes'] for v in cl.values()),'original_to_copied_dir':{'target':'forced-C/target','shared':'forced-C/shared'}});print(len(summary),'receipts',len(list(meta.glob('*.gz'))),'distinct metadata files',len(list(art.iterdir())),'full output summaries')
