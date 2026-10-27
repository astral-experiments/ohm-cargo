"""Source-matched Cargo unit graph with the seven saved compiler-proven unused extern sets."""
from pathlib import Path
import collections,json,hashlib,subprocess
d=Path(__file__).resolve().parent
f=Path('/home/dev-user/.cache/ohm-build-cutoff-20261027/unused-link-audit-20261027/test-unit-graph.json')
u=json.loads(f.read_bytes())['units'];x=json.loads((d/'nine-terminals.json').read_bytes())
def owner(unit):
 p=unit['pkg_id'];return p.split('#')[-1].split('@')[0]if p.startswith('registry+')else Path(p.split('#')[0]).name
def islib(unit):return set(unit['target']['kind'])<= {'lib','rlib','dylib','proc-macro','staticlib','cdylib'} and len(unit['target']['kind'])
def walk(indices):
 seen=set();queue=list(indices)
 while queue:
  i=queue.pop()
  if i in seen:continue
  seen.add(i);queue.extend(a['index']for a in u[i]['dependencies']if islib(u[a['index']]))
 return seen
root=Path('/home/dev-user/code/oss/ruff-ohm-wild-whole-workspace-20261026')
rev=subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip();assert rev.startswith('93526150df')
res=[]
for j in x['rows']:
 usedgroup=j['manifest_unused_extern_names'];row={'rustc_input':j['source'],'unit':j['stable_crate_id'],'exe':j['exe'],'unused_proof':usedgroup is not None}
 k=[i for i,v in enumerate(u) if v['mode']=='test' and v['target']['src_path'].endswith('/'+j['source'])]
 i,=k;entry=u[i];deps={k['extern_crate_name']:k['index']for k in entry['dependencies']if islib(u[k['index']])}
 dirty=set(j['dirty_extern_names']);assert dirty<=set(deps)
 row['binary_order_edges']=sorted(u[k['index']]['target']['name'] for k in entry['dependencies'] if u[k['index']]['target']['kind']==['bin'])
 if usedgroup is not None:
  # Use the complete compiler-proven unused set, including registry crates.
  pending=[e for n,e in deps.items() if n not in usedgroup];held=walk(pending);op={owner(u[k]) for k in held}
  row['used_root_reaches_dirty_workspace_packages']=sorted(n for n in dirty if owner(u[deps[n]])in op);row['producing_packages']=sorted({owner(u[deps[n]])for n in dirty});row['not_proven_unused_roots']=sorted(n for n in deps if n not in usedgroup)
  native_packages={k for k,vs in x['build_scripts'].items() if any(v['links'] or v['search_count'] for v in vs)}
  row['possible_exclusive_native_by_changed_direct_dependency']={n:sorted(({owner(u[z]) for z in walk([deps[n]])}-op)&native_packages) for n in sorted(dirty)}
  row['exclusive_native_filter_hits']=sorted({v for a in row['possible_exclusive_native_by_changed_direct_dependency'].values()for v in a})
 res.append(row);print(j['source'],row['binary_order_edges'],row.get('used_root_reaches_dirty_workspace_packages'),row.get('exclusive_native_filter_hits'))
out=dict(graph_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),source=rev,unit_count=len(u),rows=res);(d/'terminal-closure.json').write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
