"""Inspect nine graph-negative terminal jobs' genuine linker inputs and saved unused extern proofs."""
from pathlib import Path
from collections import Counter
import ast,hashlib,json,re,subprocess,sys
if len(sys.argv)==1:
 d=Path(__file__).resolve().parent;rows=json.loads((d/'h2-retained.json').read_bytes())['test/B']
 sel={v['trace']:v for v in rows if v['result']['parser_keys']==0};assert len(sel)==9
 p=d.parent/'first-occurrence-native-results-v1/commands/test/B/lexer-pending-indentation-edit.json';r=json.loads(p.read_bytes())
 inp=dict(expected=sorted(sel),wild=r['native_process_files']['wild'],trace_sha256={pid:d0.get('process_trace_sha256') for pid,d0 in r['native_process_trace_sha256'].items()},inventory=json.loads((d/'inventory.json').read_bytes())['test/B'])
 cmd=['dbox','ssh','charlie-ohm-relink-b-1024','--no-tmux','--','nice','-n','19','taskset','-c','30','/usr/bin/python3','-B','-c',Path(__file__).read_text(),'remote']
 o=json.loads(subprocess.check_output(cmd,input=json.dumps(inp).encode(),timeout=120));(d/'nine-terminals.json').write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
 for v in o['rows']:
  print(v['crate'],v['exe'],v['manifest_present'],v['manifest_unused_workspace_names'],v['dirty_extern_names'],v['dirty_extern_names_outside_unused'],v['link']['dirty_rust_rlibs'],v['link']['response_file'])
 sys.exit()
q=Path.home()/'.cache/ohm-233-position-qualified-20261027/first-occurrence-mixed-parser-20261027';loc=q/'receipts/test/B/lexer-pending-indentation-edit';st=q/'state/test/B';p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
i=json.load(sys.stdin); allws={r['crate']for r in i['inventory']['jobs']};dirty_files={};elf={};build_scripts={}
for line in (loc/'stdout').read_bytes().splitlines():
 o=json.loads(line)
 if o.get('reason')=='build-script-executed':
  pkg=o['package_id'];name=pkg.split('#')[-1].split('@')[0] if pkg.startswith('registry+')or 'git+' in pkg else Path(pkg.split('#')[0]).name
  if name[0].isdigit():
   tail=pkg.split('#',1)[0];name=tail.rsplit('/',1)[-1]
  build_scripts.setdefault(name,[]).append(dict(links=o.get('linked_libs',[]),search_count=len(o.get('linked_paths',[])),cfg_count=len(o.get('cfgs',[])),out_tail='/'.join(Path(o['out_dir']).parts[-3:])))
  continue
 if o.get('reason')!='compiler-artifact':continue
 for fn in o['filenames']:
  if not o['fresh'] and fn.endswith(('.rlib','.rmeta')):dirty_files[Path(fn).name]=o['target']['name'].replace('-','_')
 exe=o.get('executable')
 if exe:elf[Path(exe).name]=Path(exe)
def physical(f):
 for d,k in ((p/'native-target','target'),(p/'shared','shared')):
  if f.is_relative_to(d):return st/k/f.relative_to(d)
 raise ValueError(f)
def read(pid,img):
 real=loc/pid;r=real.read_bytes();h=hashlib.sha256(r).hexdigest();assert i['trace_sha256'][pid]==h,(pid,h,i['trace_sha256'][pid])
 for l in r.decode().splitlines():
  m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',l)
  if m and l.endswith('= 0') and Path(ast.literal_eval(m[1])).name==img:
   return [ast.literal_eval(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])],h
 raise RuntimeError(pid)
link_rows={}
for pid in i['wild']:
 a,h=read(pid,'ld.bfd');dst=Path(a[a.index('-o')+1]).name;assert dst not in link_rows
 linked=[Path(s).name for s in a if s.endswith('.rlib')]
 link_rows[dst]={'trace':pid,'trace_sha256':h,'out_basename':dst,'rust_rlib_count':len(linked),'dirty_rust_rlibs':sorted([name for name in linked if name in dirty_files]),'workspace_rlib_names':sorted([name for name in linked if name.startswith(('libruff','libty_','libty-'))]),'response_file':any(s.startswith('@')for s in a)}
rows=[]
for rec in i['inventory']['jobs']:
 if rec['trace']not in i['expected']:continue
 a,h=read(rec['trace'],'rustc');args=lambda flag:[a[n+1]for n,x in enumerate(a)if x==flag]
 extra,=[v.split('=',1)[1]for v in args('-C') if v.startswith('extra-filename=')]
 exe=rec['crate']+extra;f=physical(elf[exe]).with_suffix('.rlink-cache.json');assert exe in link_rows
 ex={x.split('=',1)[0].split(':')[-1]:Path(x.split('=',1)[-1]).name for x in args('--extern')}
 dirty=[n for n,fn in ex.items()if fn in dirty_files]
 man=json.loads(f.read_bytes())if f.is_file() else {};unused=man.get('unused_extern_names')
 rows.append(dict(crate=rec['crate'],stable_crate_id=rec['stable_crate_id'],exe=exe,source=next(x for x in a if x.endswith('.rs')),rustc_trace=rec['trace'],rustc_trace_sha256=h,dirty_extern_names=sorted(dirty),dirty_extern_names_outside_unused=sorted(set(dirty)-set(unused))if unused is not None else None,manifest_present=bool(man),manifest_sha256=hashlib.sha256(f.read_bytes()).hexdigest()if man else None,manifest_relpath=str(f.relative_to(st)),manifest_unused_extern_names=sorted(unused) if unused is not None else None,manifest_unused_workspace_names=sorted(x for x in unused if x in allws or x.startswith(('ruff','ty_'))or x=='ty') if unused is not None else None,link=link_rows[exe]))
assert len(rows)==9
print(json.dumps(dict(case='test/B/first-edit',evidence_scope='physical rustc and Wild arguments at edit; Cargo unused extern manifest from retained post-corpus output',rows=rows,build_scripts=build_scripts,dirty_rlib_names=sorted(n for n in dirty_files if n.endswith('.rlib')))))
