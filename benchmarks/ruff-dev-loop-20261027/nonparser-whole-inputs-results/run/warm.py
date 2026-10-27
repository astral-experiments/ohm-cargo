from pathlib import Path
import hashlib,json,shutil
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';Q=X/'nonparser-whole-inputs-campaign-v1';H=X/'nonparser-whole-inputs-impl-v1';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');S=Path('/dev/shm/ohm-nonparser-whole-inputs-20261027/state/test');J=lambda x:json.loads(x.read_bytes())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
out={'sources':J(Q/'fixture/manifest.json')['original'],'ruff_tree':'62d3f106c5e41f6022847f26ff8c7dc00139f7b1','runner':{p.name:sha(p) for p in (H/'worker.py',H/'process_scan.py',X/'first-occurrence-worker-v2/common.py',X/'first-occurrence-worker-v2/namespace.py')},'bound_tools':J(X/'first-occurrence-worker-v2/binding.json')['host']['host_tools'],'phases':{}}
for key in ('cold','warm-1','warm-2'):
 d=Q/'receipts/test'/key;ps=J(d/'processes.json');reg=J(d/'receipt.json');real=[s for s in ps['typed'] if s['kind']=='rustc-full'];a=[json.loads(v) for v in (d/'stdout').read_bytes().splitlines()];sm={}
 for s in real:
  if s['crate']!='ron':continue
  args=s['argv'];src=next((v for v in args if '/ron-' in v and v.endswith('.rs')),None)
  if src and src.startswith(str(P/'registry-home')):
   p=S/'registry-home'/Path(src).relative_to(P/'registry-home');rr=p
   while not (rr/'Cargo.toml').is_file():rr=rr.parent
   entry={'source_path':src,'source_sha256':sha(p),'Cargo.toml_sha256':sha(rr/'Cargo.toml'),'available_registry_checksum_files':{str(q.relative_to(rr)):sha(q) for q in (rr/'.cargo-checksum.json',rr/'.cargo-ok') if q.is_file()},'package_id':[r['package_id'] for r in a if r.get('target',{}).get('name')=='ron' and 'package_id' in r],'actual_compiler_argv':args,'exec_line_sha256':s['exec_sha256']}
   matches=list((S/'registry-home/registry/cache').glob('*/'+rr.name+'.crate'));entry['package_tarball_current_sha256']={str(q.relative_to(S/'registry-home')):sha(q) for q in matches};sm[str(s['pid'])]=entry
 out['phases'][key]={'receipt':reg,'source_rustc':[s['crate'] for s in real] if key!='cold' else len(real),'ron_actuals':sm,'setup':J(d/'setup.json'),'changed_product_names':list(J(d/'artifact-changes.json')) if key=='warm-1' else [],'logs_sha256':{p.name:sha(p) for p in (d/'stderr',d/'stdout',d/'exec-traces.tar.zst',d/'processes.json')},'fresh_false_targets':[r['target']['name'] for r in a if r.get('reason')=='compiler-artifact' and not r['fresh']] if key!='cold' else []}
 t=out['phases'][key];print(key,reg['fresh'],reg['jobs'],t['source_rustc'],[(a['source_path'],a['source_sha256'],a['package_tarball_current_sha256']) for a in sm.values()],t['changed_product_names'])
out['lock_sha256']=sha(Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027/Cargo.lock'));p=Q/'selected-evidence';p.mkdir(exist_ok=True);(p/'initial-test-freshness.json').write_text(json.dumps(out,indent=1,sort_keys=True)+'\n')
