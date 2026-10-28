from pathlib import Path
import hashlib,json,subprocess,sys
op=Path(__file__).resolve().parent;mod=op.parent/'cargo-checksum-spaced-rc17-wall-h5-path-control/namespace.py'
q='/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/rc17-spaced-full-test-h5-v1';host='charlie-ohm-loader-perf-1024'
remote=mod.read_text()+"""
import sys,os
q=Path(sys.argv[1]);assert not(q/'wall').exists();out={}
for a in 'BC':
 p=q/'receipts'/('1-'+a)/'cold/stdout'
 if not p.is_file():raise SystemExit(3)
 raw=[json.loads(l) for l in p.read_bytes().splitlines(keepends=True)if l.endswith(b'\\n')]
 items=[r for r in raw if r['reason']=='compiler-artifact' and r['target']['name']=='unicode_ident']
 if not items:raise SystemExit(3)
 names=('package_id','manifest_path','target','profile','features','filenames','executable')
 rs=[encode({k:v[k]for k in names})for v in items]
 ns,anchorrows=anchor(q/'work/ruff-target',rs)
 out[a]={'namespace':ns,'anchors_found':anchorrows,'cold_complete_at_capture':raw[-1].get('reason')=='build-finished','selected_artifact_sha256':digest(sorted(rs))}
assert out['B']['namespace'][0]==out['C']['namespace'][0]and out['B']['namespace'][1]!=out['C']['namespace'][1]
print(json.dumps(out,sort_keys=True))
"""
r=subprocess.run(['dbox','ssh',host,'--no-tmux','--','taskset','-c','28-29','python3','-B','-c',remote,q],capture_output=True)
if r.returncode:print('cold anchor not present yet',r.returncode,r.stderr.decode()[-90:]);sys.exit(3)
z=json.loads(r.stdout);ident=op/'prospective-anchors.json';assert not ident.exists();ident.write_text(json.dumps(z,sort_keys=True,indent=2)+'\n');print(ident.name,hashlib.sha256(ident.read_bytes()).hexdigest(),{k:v['namespace']for k,v in z.items()})
