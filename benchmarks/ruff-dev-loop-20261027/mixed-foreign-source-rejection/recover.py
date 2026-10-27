from pathlib import Path
import sys, json, os, subprocess as sp,shutil,hashlib
root=Path(sys.argv[1]).resolve(); main=root/'ws';ss=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf/trait-pgo-state');rt=ss/'sysroot';front=rt/'bin/rustc';driver_name='librustc_driver-774a793a844d5500.so';cargo=Path(sys.argv[2]).resolve();driver=Path(sys.argv[3]).resolve();target=root/'target'; shared=root/'shared';wrapper=root/'wrapper'
p=Path(__file__).resolve().with_name('common-guards.py')
txt=p.read_text();exec(compile('env=dict(os.environ'+txt.split('env=dict(os.environ',1)[1].split('stages=')[0].replace("'0-3'","'20-23'"),str(p),'exec'))
rr=root/'remove_files_before_macro';_,arts,kids=None,{a['target']['name']:a for a in [json.loads(l)for l in (rr/'current/stdout.jsonl').read_text().splitlines()] if a['reason']=='compiler-artifact'},json.loads((rr/'current/children.json').read_bytes())
assert [k['link_only'] for k in kids if k['crate']=='bundle']==[True]
so,direct=result(arts); meta=next(Path(f)for f in arts['bundle']['filenames']if f.endswith('.rmeta'));shutil.copyfile(meta,rr/'stale.rmeta');so.rename(rr/'stale.so')
full,kids=run(rr/'recovery-full','bundle');assert [k['link_only'] for k in kids if k['crate']=='bundle']==[False]
_,gold=result(full);shutil.copyfile(meta,rr/'repaired.rmeta')
app,kids=run(rr/'recovery-caller','app');assert [k['link_only'] for k in kids if k['crate']=='app']==[False];assert all(k['crate']!='bundle'for k in kids)
exe=Path(app['app']['executable']);out=sp.check_output([exe],text=True).splitlines();assert out==['bundle/src/lib.rs:1:1','leaf/src/lib.rs:12:51'],out
fail=(rr/'current-caller/stderr').read_text();assert 'missing source file' in fail and 'rustc_metadata::rmeta::decoder' in fail
pj=next(target.rglob('lib-leaf.public-api-hash'));j={'original_insertion_rows':json.loads((root/'observations.json').read_bytes()),'removed_producer_hash':json.loads(pj.read_bytes()),'cached_bundle_reused':True,'cached_app_exit':101,'cached_app_diagnostic':'missing source file in decoder::get_module_children at decoder.rs:1905','full_rebuilt':True,'same_app_full_compile_exit':0,'app_runtime':out,'app_sha256':sha(exe),'cached_library':direct,'forced_library':gold}
(root/'confirmation.json').write_text(json.dumps(j,indent=2)+'\n');print('same caller recovered',out,direct['rmeta']==gold['rmeta'],direct['sha256']==gold['sha256'],j['removed_producer_hash'],flush=True)
