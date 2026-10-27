from pathlib import Path
import hashlib,json,tarfile
D=Path(__file__).resolve().parent
def read(t,p):return json.load(t.extractfile(p))
def file_sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def products(t,mode,label):
 w=read(t,f'{mode}/{label}/workspace.json')
 return {p:v['result']['sha256'] for p,v in w.items() if v['result'].get('elf',False) and 'custom-build' not in v['kind']}
def own(s):return Path(s['image']).parents[2].name
out={'workspace':{},'causal':{},'controls':{}}
with tarfile.open(D/'physical-workspace.tar.gz') as t:
 for m,n in [('check',520),('build',501),('test',619)]:
  mrows={}
  for l in ('baseline-1','edit','unchanged-edit','restore','unchanged-restore'):
   rs=read(t,f'{m}/{l}/receipt.json');j=read(t,f'{m}/{l}/script-output.json')
   assert rs['exit']==0 and rs['cargo_units']==n and rs['cargo_diagnostics']==(1 if m=='test' else 0) and read(t,f'{m}/{l}/diagnostics.json')==read(t,f'{m}/baseline-1/diagnostics.json')
   before=products(t,m,'baseline-1');after=products(t,m,l);assert before.keys()==after.keys()
   outputs={x['cargo']['package_id'].split('#')[0].rsplit('/',1)[-1]:{'lines':x['raw']['lines'],'codegen':{k:x['cargo'][k] for k in ('cfgs','env','linked_libs','linked_paths')},'tree':x['out_tree']} for x in j}
   assert set(outputs)=={'ruff','ty','ty_wasm'} and all(x['tree']=={'entries':{}} for x in outputs.values())
   if l=='baseline-1':first=outputs
   for key,x in outputs.items():
    no_watch=lambda v:[line for line in v['lines'] if not line.startswith(('cargo:rerun-if','cargo::rerun-if'))]
    assert no_watch(x)==no_watch(first[key]) and x['codegen']==first[key]['codegen']
   changed=[p for p,v in after.items() if v!=before[p]];assert (len(changed)==1 if m=='test' and l!='baseline-1' else not changed)
   roles=sorted(own(x) for x in rs['executed_build_scripts'])
   assert roles==(['ruff','ty','ty_wasm'] if l in ('edit','restore') else [])
   mrows[l]={'units':n,'fresh':rs['fresh'],'processes':rs['totals'],'real_workspace_scripts':roles,'ELFs_outside_build_scripts':len(after),'ELFs_changed_from_start':sorted(changed),'CLI':{k:v['stdout'] for k,v in read(t,f'{m}/{l}/versions.json').items()}}
  out['workspace'][m]=mrows
with tarfile.open(D/'causal-check.tar.gz') as t:
 for direction in ('edit','restore'):
  base=read(t,f'check/{direction}/mtimes.json')
  out['causal'][direction]={}
  for key,x in base.items():
   r=x['library_rmeta'];s=x['script_result'];ss=x['script_stdout']
   assert r['mtime_ns']==ss['mtime_ns']<s['mtime_ns'];out['causal'][direction][key]={'rmeta_sha256':r['sha256'],'rmeta_mtime_ns':r['mtime_ns'],'script_stdout_mtime_ns':ss['mtime_ns'],'script_result_mtime_ns':s['mtime_ns'],'delta_ns':s['mtime_ns']-r['mtime_ns']}
  for suffix,cnt in [('ordinary-next-1',3),('ordinary-next-2',3),('ordinary-next-3',3),('after-private-mtime-1',0),('after-private-mtime-2',0)]:
   p=f'check/{direction}-{suffix}';r=read(t,p+'/receipt.json');times=read(t,p+'/mtimes.json');assert r['totals'].get('rustc-full',0)==cnt and r['fresh']==(514 if cnt else 520) and not r['executed_build_scripts']
   for key,x in times.items():assert x['library_rmeta']['sha256']==base[key]['library_rmeta']['sha256']
   out['causal'][direction][suffix]={'full_rustcs':cnt,'units':520,'fresh':r['fresh'],'rustc_fingerprint_reasons_file':p+'/reasons.json'}
with tarfile.open(D/'native-controls.tar.gz') as t:
 c=read(t,'result.json');assert len(c)==7
 for name,case in c.items():
  ordered=['prime','warm-original','edit','warm-edited','empty-edited','restore'];out['controls'][name]={stage:case[stage]['stdout'] for stage in ordered}
  assert all(case[s]['correct'] for s in ordered)
  assert [case[s]['stdout'] for s in ordered]==(['41']*6 if name=='watch-only' else ['41','41','83','83','83','41'])
  for stage in ordered:
   data=read(t,f'{name}/{stage}/result.json');assert data['build_returncode']==data['program_returncode']==0 and t.getmember(f'{name}/{stage}/physical.exec').size>0
if __name__=='__main__':
 import sys
 if '--write' in sys.argv:(D/'results.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
 else:assert json.loads((D/'results.json').read_bytes())==out;print('15 primary, 13 causal including baseline, and 42 external native observations verified')
