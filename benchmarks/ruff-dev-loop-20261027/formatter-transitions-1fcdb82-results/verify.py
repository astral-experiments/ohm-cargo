"""Recheck 56 captured Cargo commands, job attribution, artifact bytes, and external reader diagnostics."""
from pathlib import Path
import collections,gzip,hashlib,io,json,os,re,subprocess,sys,tarfile
root=Path(__file__).resolve().parent
h=lambda b:hashlib.sha256(b).hexdigest()
deny=re.compile(rb'openai[.](org|com|internal)|artifactory[.]|authoriz'+rb'ation: bearer|github_'+rb'pat_|ghp_[A-Za-z0-9]{16}',re.I)
def read(f):return json.loads(f.read_bytes())
plan=read(root/'plan.json');binding=read(root/'binding.json')
assert h((root/'source.patch').read_bytes())==plan['patch_sha256']and not deny.search((root/'plan.json').read_bytes())
assert all(binding['images'][k]==plan['release'][k]for k in binding['images'])
for n in ('constant','newlines'):assert binding['reader_inputs'][n+'.rs']==h((root/('readers-'+n+'.rs')).read_bytes())
ledger=json.loads(gzip.decompress((root/'physical-ledger.json.gz').read_bytes()))
summary={};all_cmd=[];work=[];artifacts={};diagnostic_sets=collections.defaultdict(set);clean_vs_warm={};result_externs={}
for tg in sorted(root.glob('small*.tar.gz')):
 flow=tg.name.split('.')[0];summary[flow]={}
 with tarfile.open(tg)as t:
  d={m.name:t.extractfile(m).read()for m in t if m.isfile()}
 for n,s in d.items():
  raw_sig,new_sig,old_len,new_len=ledger[flow+'/'+n]
  assert h(s)==new_sig and len(s)==new_len and not deny.search(s)
 get=lambda p:json.loads(d[p])
 assert get('complete.json')['settled']=='train1'
 times=sorted(z.split('/')[0]for z in d if z.endswith('/end.json'))
 assert len(times)==(8 if flow=='small-gold'else 24)
 for key in times:
  base=lambda n:key+'/'+n;r=get(base('end.json'));mode=r['mode'];group=r['group'];src=r['view'];unit=get(base('units.json'));native=get(base('all-native.json'));products=get(base('products.json'))
  assert r['source']==binding['sha_'+src]and len(unit)==r['units']and sum(u['fresh'] for u in unit)==r['fresh']
  assert (r['units'],len(get(base('diagnostics.json'))))==((58 if mode=='test'else 57),0)
  for f,sig in r['kept_raw'].items():assert sig==ledger[flow+'/'+base(f)][0]
  calls=collections.Counter(x['kind']for x in native);assert dict(calls)==r['physical']and all(c['exit']==0 for c in native)
  normal,=[u for u in unit if u['target']['name']=='ruff_formatter'and u['target']['kind']==['lib']and not u['profile']['test']]
  own={Path(f).name:products['after'][f][2]for u in unit if u['target']['name']=='ruff_formatter'for f in u['filenames']}
  oracle=r['oracle'];assert oracle['constant']['codes']==([]if src=='reversed' else ['E0425'])
  assert oracle['constant']['status']==(0 if src=='reversed' else 1)
  err=d[base('constant.stderr')];assert h(err)==oracle['constant']['diagnostics_sha256'];diagnostic_sets[src].add(h(err))
  s=oracle['constant']['metadata_sha256'];assert s in own.values()
  if mode!='check':
   assert bytes.fromhex(oracle['newlines']['stdout_hex'])==b'a\\nb\n'*4 and oracle['newlines']['status']==0
   assert oracle['newlines']['source_rlib_sha']in own.values()
  if mode=='test':
   q=oracle['harness'];assert q['harness_sha']in own.values() and q['list']==h(d[base('harness-list.stdout')])and q['entries']==len(d[base('harness-list.stdout')].splitlines())
   assert b'format_element::tests::test_normalize_newlines: test' in d[base('harness-list.stdout')].splitlines()and b'1 passed; 0 failed;'in d[base('harness-one.stdout')]
  all_cmd.append([flow,key,src,mode,r['units'],r['fresh'],r['physical'],oracle]);artifacts[flow,key]=own
  if group in ('train1','repeat-edit','repeat-restore')or (r['slot']==4 and group in('first-edit','restore')):assert len(native)==0 and all(u['fresh']for u in unit)
  if group in ('first-edit','restore')and r['slot']!=4:
   assert calls==({'full':1,'wild':1}if mode=='test'else {'full':1})
   c,=[c for c in native if c['kind']=='full'];assert c['name']=='ruff_formatter'and c['outputs']
   if mode=='test':
    row,=[u for u in unit if u['target']['name']=='ruff_formatter'and u['profile']['test']]
    ld,=[x for x in native if x['kind']=='wild'];assert ld['outputs']==[row['executable']]
   else:row=normal
   assert not row['fresh']
   changes={}
   for f in row['filenames']:
    old=products['before'][f];new=products['after'][f];assert old and new and len(old[2])==len(new[2])==64
    changes[Path(f).name]=[old[2],new[2]];assert old[2]!=new[2]
   result_externs[flow,group,mode]=[(e[0],e[1],e[2][-1])for e in c['externs_post_call']]
   work.append({'flow':flow,'group':group,'mode':mode,'unit':c['unit'],'compiler_argv_sha':c['argv_sha256'],'changed_files':changes,'check':r['physical']})
 for group in ('first-edit','restore'):
  history=[row for row in all_cmd if row[0]==flow and row[1].startswith(group+'-')]
  if history:
   v=collections.Counter()
   for x in history:v.update(x[6])
   assert v=={'full':3,'wild':1};summary[flow][group]=dict(v)
assert len(all_cmd)==56 and len(work)==12
for flow in ('small-C-B-T-B','small-B-T-C-B'):
 for row in all_cmd:
  fl,key,view,mode,*rest=row
  if fl!=flow or not key.startswith('first-edit-'):continue
  # Compare with empty edited state trained check -> build -> test -> build. Different unit suffixes for a check from build-first are retained.
  peers=[(k,v)for (f,k),v in artifacts.items()if f=='small-gold'and k.startswith('cold-')and k.endswith('-'+mode)]
  _,ref=peers[0];local=artifacts[fl,key];equal=sorted(k for k in sorted(set(local)&set(ref))if local[k]==ref[k])
  clean_vs_warm[fl+'/'+key]={'raw_equal_by_filename':equal,'warm':local,'empty':ref}
  assert row[-1]['constant']['codes']==[]
  if mode=='test':assert row[-1]['harness']['harness_sha']in ref.values()
line={(r[7]['harness']['list'],r[7]['harness']['entries'])for r in all_cmd if r[3]=='test'}
assert len(line)==1 and all(len(sigs)==1 for sigs in diagnostic_sets.values())
ext={}
for mode in ('check','build','test'):
 a=result_externs['small-C-B-T-B','first-edit',mode];b=result_externs['small-B-T-C-B','first-edit',mode]
 ext[mode]={'actual_full_argv_equal':next(r['compiler_argv_sha']for r in work if r['mode']==mode and r['flow']=='small-C-B-T-B'and r['group']=='first-edit')==next(r['compiler_argv_sha']for r in work if r['mode']==mode and r['flow']=='small-B-T-C-B'and r['group']=='first-edit'),'by_sorted_extern_slot':[[x,y]for x,y in zip(a,b)if x!=y],'slots':[len(a),len(b)]}
out={'commands':len(all_cmd),'clean_reference':clean_vs_warm,'external_constant_diagnostics':{k:sorted(v)for k,v in diagnostic_sets.items()},'harness_listing':list(next(iter(line))),'flows':summary,'all_history_work':work,'direct_inputs_across_orders':ext,'normal_newline_outputs_hex':sorted({r[7]['newlines']['stdout_hex']for r in all_cmd if 'newlines'in r[7]}),'excluded_scope':'Package ruff_formatter. No CLI or workspace timing, no native link-input equivalence. Permanent private raw files are hash-bound.'}
if '--write'in sys.argv:(root/'findings.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
else:assert read(root/'findings.json')==json.loads(json.dumps(out))
if(root/'SHA256SUMS').exists():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=root,check=True)
print('verified',len(all_cmd),len(work),'held edit/restore compilers, 4 actual Wild with changed test ELF',line)
