"""Replay the opposite committed CLI bank after a real library rebuild, then do a cold full CLI."""
from pathlib import Path
import ast,contextlib,fcntl,hashlib,json,os,re,shutil,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
from study2 import native
def run_saved(d,cmd,selector):
 so,se=d/(selector+'.stdout'),d/(selector+'.stderr');monitor(cmd,so,se);return so,se
def version(d,exe,src,reference):
 checks={}
 for name,argv,inp in [('short_version',['--version'],None),('detailed_version',['version'],None),('version',['version','--output-format','json'],None),('lint',['check','--isolated','--no-cache','--config','lint.select=["F821"]','--stdin-filename','probe.py','--output-format','concise','-'],b'print(missing)\n'),('format',['format','--isolated','--no-cache','--config','format.line-ending="lf"','--stdin-filename','probe.py','-'],b'x=1\r\n')]:
  rr=subprocess.run([str(exe),*argv],env=env,cwd=w,input=inp,capture_output=True);(d/(name+'.out')).write_bytes(rr.stdout);(d/(name+'.err')).write_bytes(rr.stderr)
  expect=reference['oracles'][name];assert(rr.returncode,rr.stdout.decode(),rr.stderr.decode())==(expect['status'],expect['stdout'],expect['stderr']),name
  checks[name]=[rr.returncode,H(rr.stdout),H(rr.stderr)]
 assert json.loads((d/'version.out').read_bytes())['commit_info']['commit_hash']==plan['heads'][src]
 return checks
def runstep(src,previous,now,tag):
 # All manipulation stays in the new H3 tmpfs. The original lower Ruff tree, released SDK and seed remain read-only.
 target_head=plan['heads'][src];
 if git('rev-parse','HEAD').decode().strip()!=target_head:go(['git','switch','--detach',target_head])
 view(src)
 root=q/'comparisons-exact-v3';root.mkdir(exist_ok=True);base=root/tag;recover=base.exists();base.mkdir(exist_ok=True);old=json.loads((q/'receipts'/previous/'result.json').read_bytes());current=json.loads((q/'receipts'/now/'result.json').read_bytes())
 baseline=base/'ordinary';baseline.mkdir(exist_ok=True);(baseline/'trace').mkdir(exist_ok=True)
 # Diagnostic trace is outside any clock; log the preparation-time dirty reason and actual same-native workload.
 env['CARGO_LOG']='cargo::compiler::fingerprint=info'
 if not recover:run_saved(baseline,['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',baseline/'trace/run',*plan['command']],'cargo')
 env.pop('CARGO_LOG');ord_calls=native(baseline);put(baseline/'procs.json',ord_calls)
 oldbin,=[x for x in json.loads((q/'receipts'/now/'procs.json').read_bytes())if x.get('crate_type')=='bin'and x.get('kind')=='full'];actual=oldbin['argv'];assert 'crates/ruff/src/main.rs'in actual
 fullargs=actual[1:];refcache=current['stored_terminal'];out=Path(refcache['root']);exe=out/'ruff'
 assert out.is_relative_to(t);live={k:sha(current['lib'][k])for k in ('rlib','metadata')};header=go(['rustc','+ohm','-Zls=root',current['lib']['metadata']]).stdout;assert ('public_hash '+current['lib']['public']).encode() in header and ('private hash '+current['lib']['private']).encode()in header;put(base/'current_library.json',{'first':current['lib'],'actual':live,'header_sha256':H(header)});
 expect=version(baseline,exe,src,current);natural_sha=sha(exe)
 oldbank=Path(old['stored_terminal']['bank']);saved=out.parent/('saved-output-v3-'+tag);assert not saved.exists();out.rename(saved)
 records={}
 try:
  part=base/'partial';part.mkdir();(part/'trace').mkdir()
  out.mkdir();shutil.copytree(oldbank,out,dirs_exist_ok=True);assert all(sha(out/n)==v[1]for n,v in old['stored_terminal']['original'].items()) and not exe.exists()
  args=list(fullargs);args[args.index('crates/ruff/src/main.rs')]=str(out/'ruff.rlink');args+=['-Z','link-only']
  # This is the cached command construction in the shipping Cargo source. Shell, SDK, working tree and every --extern path remain the current ones.
  trace=['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o']
  run_saved(part,[*trace,part/'trace/run','rustc','+ohm',*args],'rustc');jobs=native(part);put(part/'procs.json',jobs)
  assert [x['kind']for x in jobs if x['kind']in('full','partial')and os.path.samefile(x['image'],sdk/'bin/rustc')]==['partial'] and sum(x['kind']=='wild'for x in jobs)==1
  assert {k:sha(current['lib'][k])for k in live}==live
  records['partial']={'elf':sha(exe),'oracles':version(part,exe,src,current),'previous_bank':old['head'],'current_lib':current['lib'],'argv':args}
  out.rename(out.parent/('diagnostic-partial-v3-'+tag));out.mkdir();(out/'ruff.rlink-objects').mkdir()
  # The captured rustc uses a workspace-level incremental root. Swap that root to an empty private directory for a truly cold frontend/CGU pass. The full source/compiler args and .rmeta externs are identical at the same canonical locations.
  inc=Path(next(x.split('=',1)[1]for x in fullargs if x.startswith('incremental=')));assert inc.is_relative_to(t/'debug/incremental')and inc.is_dir()
  held=inc.parent/('held-'+tag);inc.rename(held);inc.mkdir()
  gold=base/'empty-full';gold.mkdir();(gold/'trace').mkdir()
  try:
   # main.rs had zero compiler-reported env deps. Supply precisely the actual successful package build script values, including commit/date, for both the ordinary and the clean comparison.
   env2=dict(env);env2.update(dict(current['build_script']['env']));env2.update({'CARGO_MANIFEST_DIR':str(w/'crates/ruff'),'CARGO_MANIFEST_PATH':str(w/'crates/ruff/Cargo.toml'),'CARGO_PKG_NAME':'ruff','CARGO_PKG_VERSION':'0.17.0','CARGO_CRATE_NAME':'ruff','CARGO_BIN_NAME':'ruff','CARGO_PRIMARY_PACKAGE':'1','OUT_DIR':current['build_script']['out_dir']})
   dyn=[str(Path(e[0]).parent)for e in oldbin['externs'].values()if e[0].endswith('.so')];env2['LD_LIBRARY_PATH']=os.pathsep.join(dict.fromkeys(dyn+[str(sdk/'lib')]))
   argv=[*trace,gold/'trace/run','rustc','+ohm',*fullargs];go0=subprocess.run(list(map(str,argv)),cwd=w,env=env2,capture_output=True);(gold/'rustc.stdout').write_bytes(go0.stdout);(gold/'rustc.stderr').write_bytes(go0.stderr);assert go0.returncode==0,go0.stderr[-1300:]
   jobs=native(gold);put(gold/'procs.json',jobs);assert [x['kind']for x in jobs if x['kind']in('full','partial')and os.path.samefile(x['image'],sdk/'bin/rustc')]==['full']and sum(x['kind']=='wild'for x in jobs)==1
   assert {k:sha(current['lib'][k])for k in live}==live
   records['empty_full']={'elf':sha(exe),'oracles':version(gold,exe,src,current),'incremental':str(inc),'physically_empty_before':True,'command':fullargs,'inputs':oldbin['externs']}
  finally:
   inc.rename(inc.parent/('diagnostic-incremental-'+tag));held.rename(inc)
 finally:
  if out.exists():out.rename(out.parent/('diagnostic-full-v3-'+tag))
  saved.rename(out)
 rows={'actual_library':live,'source':src,'previous':previous,'natural_elf':natural_sha,'required_native':current['cli']['sha256'],'observed':records,'same_raw':len({natural_sha,records['partial']['elf'],records['empty_full']['elf']})==1,'same_semantics':expect==records['partial']['oracles']==records['empty_full']['oracles'],'status':0};put(base/'result.json',rows);guard();print(tag,rows['same_raw'],rows['same_semantics'],[natural_sha,records['partial']['elf'],records['empty_full']['elf']],flush=True)
def main():
 assert(q/'primary.json').exists()
 with(p/'native-measure.lock').open('rb')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);runstep('B','A-train-1','B-edit','A-to-B');runstep('A','B-repeat','A-restore','B-to-A');view('A');put(q/'compared.json',{'status':0,'directions':2,'source':plan['heads']['A']})
if __name__=='__main__': main()
