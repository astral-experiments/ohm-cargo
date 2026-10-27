"""Export only ordinary Cargo artifacts, successful process types and known hashes; omit environment and read buffers."""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,stat,struct,subprocess as sp,sys
h=Path('/home/dev-user/.cache/ohm-mixed-release-pilot-20261027');d=Path('/mnt/devbox-scratch/dev-user/ohm-mixed-interface-20261027');out=h/'public-scoped-release';out.mkdir()
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def load(p):return json.loads(p.read_bytes())
for name in ('run','ordinary','fullarchive-v3','tested-run-v3','tested-bridges-v3','cargo-unit-tested','cargo-inherited-tested'):assert (h/(name+'.rc')).read_text().strip()=='0',name
# The printed rustc argv have no environment fields, so select just the argument needed to substantiate phase.
stages={'pair':['prime','prime-fresh','edit1','edit1-fresh','restore','restore-fresh','edit2','edit2-fresh','tested-restore','tested-restore-fresh','tested-edit','tested-edit-fresh'],'forced':['forced-restore','forced-restore-fresh','forced-edit','forced-edit-fresh','forced-same-input-0','forced-same-input-0-fresh','forced-same-input-1','forced-same-input-1-fresh','tested-full-restore','tested-full-restore-fresh','tested-full-edit','tested-full-edit-fresh']}
for arm,labels in stages.items():
 for label in labels:
  q=h/'evidence'/arm/label;r=load(q/'result.json'); compiler=[]
  for pid,name,phase in r['procs']:
   a=load(q/('rustc-'+str(pid)+'.json'));assert a[a.index('--crate-name')+1]==name
   recipe=next((arg.split('=',1)[1] for arg in a if arg.startswith('ohm-checked-mixed-rlink=')),None);before=r['before'].get(recipe);after=r['after'].get(recipe)
   assert phase==('HIR-and-native-link' if recipe is not None and before is not None and before==after else 'checked-full-fallback' if recipe is not None else 'plain-link-only' if any(arg in ('-Zlink-only','link-only') for arg in a) else 'full')
   entry={'pid':pid,'crate':name,'phase':phase,'argv_sha256':digest(a)}
   if recipe is not None:entry.update(checked_recipe_name=Path(recipe).name,prior_sha256_mtime_ns=before,next_sha256_mtime_ns=after)
   compiler.append(entry)
  native=[]
  for kind,ids in r['native'].items():
   for pid in ids:
    f=q/('exec.'+str(pid));matches=[]
    for l in f.read_text(errors='replace').splitlines():
     hit=re.match(r'execve\("(.*?)", (\[.*?\]), .*\) += 0$',l)
     if hit and Path(hit[1]).name==kind:matches.append(ast.literal_eval(hit[2]))
    assert len(matches)==1;args=matches[0];native.append({'pid':pid,'executable':kind,'argv_sha256':digest(args)})
  members=[]
  for line in (q/'stdout').read_bytes().splitlines():
   a=json.loads(line)
   if a.get('reason')=='compiler-artifact':
    unit={'case':a['target']['name'],'kind':a['target']['kind'],'crate_types':a['target']['crate_types'],'package_id_sha256':digest(a['package_id']),'profile':a['profile'],'features':a['features']}
    members.append([digest(unit),unit['case'],a['fresh']])
  assert len(members)==r['units'] and sorted(i[1] for i in members if not i[2])==sorted(r['dirty'])
  write(out/'stages'/arm/(label+'.json'),{'source':r['source'],'cargo':r['cargo'],'compiler_driver':r['driver'],'units':r['units'],'unit_roster_sha256':digest(sorted(i[:2] for i in members)),'fresh_false':sorted(i[:2] for i in members if not i[2]),'crate_processes':compiler,'native_processes':native,'discovery_rustcs':r['discovery'],'artifacts':r['artifacts']})
for a,b in {'empty-prime.json':'initial.json','forced-comparison.json':'same-state-intermediate.json','tested-ruff-comparison.json':'same-state-final.json','same-input-archives-v3/archives.json':'earlier-tested-image-identical-full/archives.json','same-input-archives-v3/comparison.json':'earlier-tested-image-identical-full/comparison.json','ordinary-bridges/result.json':'intermediate-ordinary-bridges.json','ordinary-tested-bridges/result.json':'final-ordinary-bridges.json','cargo-unit-tested.json':'tests/cargo-unit.json','cargo-inherited-tested.json':'tests/cargo-inherited.json'}.items():write(out/b,load(h/a))
allfiles=load(h/'forced-inputs.json');pdict=dict(allfiles);assert len(pdict)==671
modes=[]
for dep,sh in pdict.items():
 x=(h/'pair'/dep).stat();y=(h/'forced'/dep).stat();modes.append([dep,sh,oct(stat.S_IMODE(x.st_mode)),oct(stat.S_IMODE(y.st_mode)),(x.st_dev,x.st_ino)!=(y.st_dev,y.st_ino)])
assert all(x[2]==x[3] and x[4] for x in modes)
write(out/'warm-copy.json',{'recorded_at_copy':'The initialization checked all artifact contents, mtimes and distinct inodes; retained data store the content hashes. Live mode/inode validation below was collected after the oracle.','original_number_of_outputs':len(pdict),'files':modes})
# The same production decoder used on both full/full baselines is reusable for final ordinary outputs.
text=(h/'release-sameinput-ar-v3.py').read_text();context={'h':h,'d':d,'sp':sp,'struct':struct,'sha':sha,'Path':Path,'json':json,'hashlib':hashlib};exec(text[text.index('def fol('):text.index("cs=('ruff_wasm'")],context);final={}
for cr in ('ruff_wasm','ty_wasm'):
 a=context['inspect']('pair','tested-edit',cr);b=context['inspect']('forced','tested-full-edit',cr)
 assert [x[1] for x in a['cgus']]==[x[1] for x in b['cgus']] and a['symbol_to_member_ordinal']==b['symbol_to_member_ordinal'] and a['ordinary']==b['ordinary'] and a['remaining_after_exhaustive_filename_decode']==b['remaining_after_exhaustive_filename_decode']=='00727573742d656e642d66696c65'
 final[cr]={'checked':a,'full':b}
write(out/'final-archives.json',final)
checks={'ruff_head':'93526150df078af7dd8fc4226cdcc469539d2001','historical_reverse':'3ea20f6161cbf59cb56595dfb634ec24bfa82f0b','patch_sha256':'08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff','cargo_head':'190d261a8546f121e3aa1adf237d85e02164eb18','cargo_sha256':'0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1','intermediate_cargo_head':'39ff222494510e15d59a2a2a64b8f578975d6b45','intermediate_cargo_sha256':'7d8a2d6715e0275308194508c70a4d49cb4c281d462c6d14b222ff4f5ecc1572','rustc_head':'b5fb832c70e8d0f353e9663a6e4f6e1409ae5eba','rustc_sha256':'7c31057e86f800e313b7d32080c7a5abaa7b92fef92254ac21b2e43febf16384','command':'cargo +ohm build --locked --offline -p ruff_wasm -p ty_wasm --message-format=json','unscored':True}
write(out/'inputs.json',checks);assert sha(d/'parser.patch')==checks['patch_sha256'];shutil.copy2(d/'parser.patch',out/'historical-parser.patch')
for name in ['release-ruff.py','release-forced.py','release-tested-ruff-v3.py','release-tested-bridges-v3.py','release-sameinput-ar-v3.py','export-scoped-release.py']:
 target=out/'reproduce'/name;target.parent.mkdir(exist_ok=True);shutil.copy2(h/name,target)
print('Exported 24 command observations, all release outputs/ordinary bridges, cache boundary and 12 unit controls.',flush=True)
