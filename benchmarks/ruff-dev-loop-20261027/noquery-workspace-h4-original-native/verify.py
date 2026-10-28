"""Check all 16 process rosters and output commitments, each encoded proof and the independent B/C input identity."""
from collections import Counter
from pathlib import Path
import hashlib,json,sys,tarfile
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here));from elf_gate import permitted_linker_width
h=lambda b:hashlib.sha256(b).hexdigest()
stamps={'O':'537fc98a7d00dcf2','A':'537fc98a7d00dcf2','B':'a60a9fe99525a185','C':'a60a9fe99525a185'}
def native_path(arm,n):
 p=Path(n);assert not p.is_absolute() and '..' not in p.parts and str(p)==n and p.parts[0]=='target'
 v=p.parts
 if v[:4]==('target','debug','build','workspaces'):
  assert len(v)>=9 and v[4:6]==('38b7ca2992c44384','v2-'+stamps[arm]);return '/'.join((*v[:5],'@verified-compiler@',*v[6:]))
 return n
def safe_units(a,rows):
 assert len(rows)==619;fixed=[]
 for v in rows:
  assert set(v)=={'package_id','manifest_path','target','profile','features','filenames','executable'}
  for k in (v['manifest_path'],v['target']['src_path'],v['package_id']):assert len(k['exact_sha256'])==64
  v['filenames']=[native_path(a,n) for n in v['filenames']]
  if v['executable'] is not None:v['executable']=native_path(a,v['executable'])
  fixed.append(json.dumps(v,sort_keys=True,separators=(',',':')))
 return sorted(fixed)
def selftest():
 start='target/debug/build/workspaces/38b7ca2992c44384/v2-';tail='/ruff/9c601305a3f3b4b8/out/ruff-9c601305a3f3b4b8'
 assert native_path('O',start+stamps['O']+tail)==native_path('C',start+stamps['C']+tail)
 assert native_path('A',start+stamps['A']+tail+'X')!=native_path('B',start+stamps['B']+tail)
 for invalid in (start+stamps['B']+tail,start.replace('38b7ca2992c44384','alternate')+stamps['A']+tail,'/tmp/out','target/debug/../ruff'):
  try:native_path('O',invalid)
  except AssertionError:continue
  raise AssertionError(invalid)
 return True
assert selftest()
with tarfile.open(Path(sys.argv[1]) if len(sys.argv)>1 else here/'observations.tar.gz') as f:
 def get(k):return json.load(f.extractfile(k))
 top=get('admission.json');assert top['scored']==0 and top['native_commands']==16 and top['exit_code']==1 and not top['workspace_timing_eligible'] and top['first_failure']=='AssertionError: roster'
 table={};fixed=None;diagnostics=None;order0=None;elf0={};cross={};fullrow=None;unrevised={}
 for a in 'OABC':
  forms=[];last=None;d0=None;rows0=None;table[a]=[];data={}
  for k in ('cold','first','settled','settled2'):
   pk=a+'/'+k+'/';s=get(pk+'summary.json');rows=get(pk+'cargo-rows.json');n=get(pk+'native.json');p=get(pk+'processes.json');ts=get(pk+'trace-commitments.json');raw=get(pk+'raw-host.json')
   assert s['elapsed_ns'] is None and s['arm']==a and s['step']==k and s['units']==len(rows)==619 and len(n)==110 and len(s['executables'])==102 and set(s['executables'])<=n.keys()
   assert Counter(x[5] for x in rows if x[7])=={True:84,False:18} and sum(x[6] for x in rows)==s['fresh'] and s['fresh']==(0 if k=='cold' else 563 if k=='first' and a!='C' else 619)
   order=sorted(json.dumps(row[:6]+row[7:]) for row in rows);assert order0 is None or order0==order;order0=order
   typed=safe_units(a,get(pk+'full-typed-rows.json'));assert fullrow is None or typed==fullrow;fullrow=typed;unrevised[a]=s['roster']
   assert not diagnostics or s['diagnostics']==diagnostics;diagnostics=s['diagnostics'];assert not fixed or fixed==s['cli'];fixed=s['cli']
   assert s['cli']['listings']['stdlib'][0]==4 and s['cli']['listings']['ty_server'][0]==200 and 'E712' in s['cli']['lint']
   assert all('exec.'+str(r[0]) in ts for r in [*p['jobs'],*p['linkers'],*p['queries']]) and len(p['cargo'])==1 and not p['observer_queries']
   counts={'rustc':dict(Counter(t[2] for t in p['jobs'])),'wild':sum(t[1] for t in p['linkers']),'system':sum(not t[1] for t in p['linkers']),'queries':len(p['queries'])};assert counts==p['counts']==s['processes']
   if k=='cold':assert counts['rustc'].get('full',0)>600 and not counts['rustc'].get('link-only',0) and counts['wild']>180
   elif a!='C' and k=='first':assert [t[1] for t in p['jobs'] if t[2]=='full']==['ron'] and counts=={'rustc':{'full':1,'link-only':50},'wild':50,'system':0,'queries':0}
   else:assert counts=={'rustc':{},'wild':0,'system':0,'queries':0}
   if k in ('cold','first'):
    rec=get(pk+'proof.json');complete=k=='first' or a=='C';optional=a=='C' or (a=='B' and k=='cold');assert rec['complete']==complete and bool(rec['optional_blake3'])==optional and rec['cargo_format']==(4 if complete else 2)
    assert rec['host_artifact_commitments']['ron.d']==rec['depfile_sha256'] and rec['host_artifact_commitments']['dep-lib-ron']==rec['encoded_sha256']
    assert len(rec['effective_inputs'])==(45 if complete else 0) and len(rec['optional_inputs'] or [])==(45 if optional else 0)
    assert len(rec['regular_inputs'])==(45 if complete and not optional else 0)
    assert s['proof']==[rec['depfile_sha256'],rec['encoded_sha256'],rec['cargo_seal']]
    for path,pathsig,algo,signature,bytes_ in [*rec['regular_inputs'],*(rec['optional_inputs'] or [])]:
     assert len(pathsig)==len(signature)==64 and algo in ('sha256','blake3') and isinstance(bytes_,int) and bytes_>=0
    el=get(pk+'elf.json');assert all(el[path]['raw']==val for path,val in n.items());data[k]=el
    if k=='cold':d0=el
    else:
     assert el.keys()==d0.keys() and all(x==d0[path] or (a!='C' and permitted_linker_width(d0[path],x)) for path,x in el.items())
    forms.append(rec)
   else:assert n==last
   table[a].append({'phase':k,'fresh':s['fresh'],'processes':counts,'raw_matches_prev':sum(last.get(nm)==h for nm,h in n.items()) if last else None});last=n
  elf0[a]=data
  if a=='B':assert forms[0]['optional_inputs']==forms[1]['regular_inputs'];explicit=forms[1]['regular_inputs']
  if a=='C':assert forms[0]['optional_inputs']==forms[1]['optional_inputs'] and (forms[0]['optional_inputs']==explicit)==top['actual_first_optional_inputs_equal_independent_explicit_inputs']
 assert unrevised['O']==unrevised['A']!=unrevised['B']==unrevised['C']
 decoder=json.loads((here/'decoded-elf.json').read_bytes());transfer=json.loads((here/'transfer.json').read_bytes());assert len(decoder['products'])==8 and set(decoder['differential'])=={'ruff-main','ty-main','ruff-test','ty-test'}
 for role,check in decoder['differential'].items():
  assert check['all_code_data_and_unclaimed_ELF_bytes_identical'] and check['exact_decoded_debug'] and check['namespace_evidence_pass']
  assert set(check['payload_differences'])=={'.note.gnu.build-id','.debug_info','.debug_macro','.debug_str'} and not check['section_metadata_differences']
  x,y=[decoder['products'][a+'-'+role] for a in 'AB'];assert x['sections'].keys()==y['sections'].keys() and x['file_size']==y['file_size'] and x['all_other_bytes']==y['all_other_bytes']
  assert x['debug_strings']['canonical_inventory']==y['debug_strings']['canonical_inventory'] and len(x['debug_strings']['actual_namespace_spellings'])==len(y['debug_strings']['actual_namespace_spellings'])==1
  for arm,z in zip('AB',(x,y)):
   assert z['raw_sha256']==transfer['files'][arm+'-'+role] and all('DW_AT_comp_dir' in s for s in z['info']['namespace_attributes']) and z['info']['namespace_attributes']
  for s in ['info','macro']:
   assert x[s]['lines']==y[s]['lines']>10000 and x[s]['decoded']==y[s]['decoded'] and x[s]['stderr_len']==y[s]['stderr_len']==0
 def witness(name):
  path=Path(name);entry=path.name;assert entry=='ruff' or entry=='ty' or entry in ('ruff-9c601305a3f3b4b8','ty-9f994ba4bc9039c1')
  return entry.split('-')[0]+('-main' if name in ('target/debug/ruff','target/debug/ty') else '-test')
 for a in 'ABC':
  cross[a]={}
  for k in ('cold','first'):
   base={native_path('O',n):v for n,v in elf0['O'][k].items()};candidate={native_path(a,n):v for n,v in elf0[a][k].items()};assert base.keys()==candidate.keys() and len(base)==110
   diff=[n for n in base if base[n]!=candidate[n]];width=[n for n in diff if permitted_linker_width(base[n],candidate[n])];others=sorted(set(diff)-set(width))
   for n in others:
    role=witness(n);assert a in 'BC' and [base[n]['raw'],candidate[n]['raw']]==[transfer['files'][u+'-'+role] for u in 'AB'],(a,k,n)
   assert len(others)==(0 if a=='A' else 4)
   cross[a][k]={'raw_equal':110-len(diff),'registered_wild_width_only':width,'decoded_jemalloc_source_directory':others}
 print(json.dumps({'native_cargo_commands':16,'scored':0,'literal_roster_admission':False,'original_failure':top['first_failure'],'all_619_other_fields_and_typed_output_components_identical':True,'attested_inputs_equal_old_Cargo_forced_new_rustc':top['actual_first_optional_inputs_equal_independent_explicit_inputs'],'actual_rosters':unrevised,'phases':table,'against_source_matched_O':cross},sort_keys=True,indent=2))
