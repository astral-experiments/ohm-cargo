"""Read five existing file/argument receipt pairs; never stat/read the original linker payloads."""
import collections
import hashlib
import itertools
import json
from pathlib import Path
import socket

base=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028/whole-wild-width-v2')
assert socket.gethostname()=='charlie-ohm-c5-check-1025'

def sha(value): return hashlib.sha256(value).hexdigest()
def read(p,digest=None):
 value=p.read_bytes(); assert digest is None or sha(value)==digest,(p,sha(value),digest); return json.loads(value)
target='e2e-6a4ba41917b202dd'; r=read(base/'targets'/target/'all-widths.json','cf759d32f165dd6819eec5b2e2522e1be5902a7c30e6d75d3949c2da0b221b01'); roles={}

def family(p):
 b=Path(p).name
 if b=='symbols.o':return 'rustc_symbols_object'
 if b.endswith('.rcgu.o'):return 'crate_codegen_object'
 if b.startswith('libron-') and b.endswith('.rlib'):return 'ron_rlib'
 if b.endswith('.rlib'):return 'other_rlib'
 if b in ('Scrt1.o','crt1.o','crti.o','crtn.o','crtendS.o','crtbeginS.o'):return 'gcc_and_system_startup'
 if b.endswith('.res'):return 'gcc_resolution'
 if b.endswith('.so') or '.so.' in b:return 'shared_library_or_linker_script'
 if b.endswith('.a'):return 'native_static_archive'
 if b.endswith('.d'):return 'make_depfile'
 return 'other'

def short(p):return str(p).replace('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028/ruff-evaluation-v2/canonical/','<work>/').replace('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028/toolchain/','<sdk>/')

def subst(p,v):
 return v if v!=p else short(v)

def labels(arg):
 if arg.startswith('-plugin-opt=-fresolution='):return 'gcc_resolution_path'
 if arg.startswith('-L') and arg.endswith('/raw-dylibs'):return 'rustc_raw_dylib_directory'
 if arg.endswith('/symbols.o'):return 'rustc_symbols_path'
 if arg.endswith('.rcgu.o'):return 'crate_codegen_object_path'
 return 'other'

for key,rr in r['recipes'].items():
 phase=rr['phase'];role=phase+'#'+str(rr['occurrence']); assert role not in roles
 af=rr['raw_argv_file'];ff=rr['raw_input_file'];args=read(base/af['file'],af['sha256']);files=read(base/ff['file'],ff['sha256']);cap=read((base/ff['file']).parent/'capture.json')
 assert sorted(v['width'] for v in cap['widths'])==list(range(1,17)) and all(v['plain_sha256']==v['depfile_sha256'] and v['plain_exit']==v['depfile_exit']==0 for v in cap['widths'])
 groups=collections.defaultdict(list)
 for k,item in files.items():groups[family(k)].append((k,item))
 def portable(k):return k if '/' not in k else Path(k).name
 roles[role]=(args,files,{'recipe':key,'argv_line_keys':len(args),'literal_inputs':len(files),'role':phase,'ordinal':rr['occurrence'],'raw_recipe_file_sha256':af['sha256'],'raw_input_file_sha256':ff['sha256'],'groups':{k:{'count':len(items),'bytes':sum(y['bytes'] for _,y in items)} for k,items in sorted(groups.items())},'ron':[[Path(k).name,y['sha256'],y['bytes']]for k,y in groups['ron_rlib']],'external':[[family(k),portable(k),Path(y['path']).name,y['sha256'],y['bytes']]for k,y in sorted(files.items())if family(k)not in ('crate_codegen_object','ron_rlib','other_rlib','rustc_symbols_object')],'raw_dylibs_empty':cap['special_inputs']['raw_dylibs_empty_directory'],'symbols':cap['special_inputs']['symbols_sha256'],'gcc_resolution':cap['special_inputs']['resolution_sha256'],'default_output':cap['raw_sha256'],'widths':{str(v['width']):v['plain_sha256'] for v in cap['widths']},'direct_arg_families':dict(collections.Counter(labels(a)for a in args)),'named_libraries':[a for a in args if a.startswith('-l')], 'search_directories':[short(a[2:])for a in args if a.startswith('-L') and not a.endswith('/raw-dylibs')]})

pairs={}
for left,right in [('selected-observer#1','selected-observer#2'),('selected-observer#2','repeat-observer#1'),('selected-composed#1','repeat-composed#1'),('repeat-observer#1','repeat-composed#1')]:
 a,u,_=roles[left];b,v,_=roles[right];assert len(a)==len(b);d=[(labels(x),labels(y))for x,y in zip(a,b,strict=True)if x!=y];inter=set(u)&set(v); renamed_u=set(u)-set(v);renamed_v=set(v)-set(u); diff_contents=[k for k in inter if u[k]['sha256']!=v[k]['sha256'] or u[k]['bytes']!=v[k]['bytes']];pd=[k for k in inter if u[k]['path']!=v[k]['path']];
 content_roster=lambda files: collections.Counter((family(k),item['sha256'],item['bytes'])for k,item in files.items());cu,cv=content_roster(u),content_roster(v)
 pairs[left+' -> '+right]={'argv_differences':dict(collections.Counter(x+' -> '+y for x,y in d)),'same_literal_paths':len(inter),'differing_same_path_content':[Path(k).name for k in sorted(diff_contents)],'differing_same_path_resolution':[Path(k).name for k in sorted(pd)],'vanished_path_types':dict(collections.Counter(family(k)for k in renamed_u)),'appeared_path_types':dict(collections.Counter(family(k)for k in renamed_v)),'content_multiset_identical':cu==cv,'removed_contents':len(list((cu-cv).elements())),'added_contents':len(list((cv-cu).elements()))}
print(json.dumps({'target':target,'source':'stock resolved native closure, recorded on -17 candidate Cargo, see release-specific -18 screen separately','roles':{k:v[2]for k,v in sorted(roles.items())},'pairs':pairs},sort_keys=True,indent=2))
