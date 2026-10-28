"""Resolve which native proc macros actually load, and calibrate compiler-output-based negatives."""
from pathlib import Path
import collections,fcntl,json,os,re,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
from study2 import native
dest=q/'macro-guard';dest.mkdir()
d=ram/'macro-guard';d.mkdir()
source={'macroprobe.rs':r'''extern crate proc_macro;
use proc_macro::TokenStream;
#[proc_macro] pub fn read(_tokens:TokenStream)->TokenStream {
    format!("{:?}",std::env::var("RUFF_COMMIT_HASH").unwrap()).parse().unwrap()
}''','read.rs':'fn main(){println!("{}", macroprobe::read!());}\n','unused.rs':'fn main(){println!("no-observer");}\n','wrapped.rs':'macro_rules! outer {()=>{env!("RUFF_COMMIT_HASH")}} fn main(){println!("{}",outer!());}\n'}
for n,v in source.items():(d/n).write_text(v)
go(['rustc','+ohm','--edition=2024','--crate-type=proc-macro','--crate-name=macroprobe',d/'macroprobe.rs','-o',d/'libmacroprobe.so'])
def test(name,params,en,exe,dep,expect,tool=False):
 folder=d/name;folder.mkdir(exist_ok=True);out=dest/name;out.mkdir();(out/'trace').mkdir()
 envx=dict(en);envx['LD_DEBUG']='files';envx['LD_DEBUG_OUTPUT']=str(folder/'ld')
 cmd=['rustc','+ohm',*params,'-Zbinary-dep-depinfo','-Zself-profile='+str(folder/'profile'),'-Zself-profile-events=generic-activity'];tr=['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',str(out/'trace/run')]
 z=subprocess.run(tr+list(map(str,cmd)),env=envx,cwd=w,capture_output=True);(out/'rustc.stdout').write_bytes(z.stdout);(out/'rustc.stderr').write_bytes(z.stderr);assert z.returncode==0,(name,z.stderr[-1200:])
 r=subprocess.run([str(exe)]+(['version','--output-format','json']if tool else[]),env=en,cwd=w,capture_output=True);assert r.returncode==0 and expect.encode()in r.stdout,(name,r.stderr,r.stdout)
 raw=dep.read_bytes();(out/'dep-info.d').write_bytes(raw)
 native_pids=[p.name.rsplit('.',1)[-1]for p in(out/'trace').glob('run.*')if re.search(rb'execve\("/[^"]+/toolchains/ohm/bin/rustc",.*\)\s+= 0$',p.read_bytes(),re.M)]
 assert len(native_pids)==1,native_pids
 lfile=folder/('ld.'+native_pids[0]);logs=lfile.read_text(); sels=[x.strip()for x in logs.splitlines()if ('calling init:'in x or 'dynamically loaded by'in x)and ('/debug/build/'in x or 'macroprobe.so'in x)]
 # The self profiler registers these exact generic event names only when the expansion is entered, including an incremental macro expansion-cache hit.
 prof,=folder.glob('profile*/*.mm_profdata') if (folder/'profile').is_dir() else folder.glob('profile*.mm_profdata')
 pdb=prof.read_bytes();event_names=['expand_proc_macro','expand_attr_proc_macro_outer','expand_derive_proc_macro_outer'];events={k:pdb.count(k.encode())for k in event_names}
 dyn=sorted({os.fsdecode(m)for m in re.findall(rb'/[^\s]+?\.so(?=[\s:\n]|$)',raw)if b'/target/debug/'in m or b'macroprobe'in m})
 refs={'subject':name,'raw_compiler_exec':sha(next(p for p in(out/'trace').glob('run.*')if p.name.rsplit('.',1)[-1]==native_pids[0])),'getenv':en.get('RUFF_COMMIT_HASH'),'status':r.returncode,'runtime':r.stdout.decode(),'ld_debug_sha':sha(lfile),'native_workload_loaded':sels,'binary_dep_dynamic':dyn,'all_env_deps':[x.decode()for x in raw.splitlines()if x.startswith(b'# env-dep:')],'self_profile_sha':sha(prof),'event_dictionary_occurrences':events,'full_dep_info_sha':H(raw),'command':list(map(str,cmd))};put(out/'result.json',refs);print(name,len(dyn),len(sels),events,flush=True);return refs
args=next(z['argv'][1:] for z in json.loads((q/'receipts/A-restore/procs.json').read_bytes())if z.get('crate_type')=='bin')
with (p/'native-measure.lock').open('rb')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);view('A');data={}
 for name,cfile,head in [('unread','unused.rs','A'),('rawA','read.rs','A'),('rawB','read.rs','B'),('wrapped','wrapped.rs','A')]:
  folder=d/name;en=dict(env);en['RUFF_COMMIT_HASH']=plan['heads'][head];target=folder/'native';df=folder/'probe.d';params=['--edition=2024','--crate-name','probe','--extern','macroprobe='+str(d/'libmacroprobe.so'),'--emit=dep-info='+str(df)+',link='+str(target),d/cfile];data[name]=test(name,params,en,target,df,'no-observer'if name=='unread'else en['RUFF_COMMIT_HASH'])
 label='ruff-head-A';folder=d/label;folder.mkdir();(folder/'out').mkdir();(folder/'objects').mkdir()
 args[args.index('--out-dir')+1]=str(folder/'out')
 for i,s0 in enumerate(args):
  if s0.startswith('incremental='):args[i]='incremental='+str(folder/'incremental')
  if s0.startswith('temps-dir='):args[i]='temps-dir='+str(folder/'objects')
 prior=json.loads((q/'receipts/A-repeat/result.json').read_bytes());en=dict(env);en.update(dict(prior['build_script']['env']));en['CARGO_MANIFEST_DIR']=str(w/'crates/ruff');en['CARGO_PKG_VERSION']='0.17.0'
 data[label]=test(label,args,en,folder/'out/ruff',folder/'out/ruff.d',plan['heads']['A'],True)
 assert all('macroprobe' in str(data[n]['native_workload_loaded']) and data[n]['event_dictionary_occurrences']['expand_proc_macro']>0 and not data[n]['all_env_deps']for n in('rawA','rawB'))
 assert not data['unread']['native_workload_loaded']and not data['unread']['event_dictionary_occurrences']['expand_proc_macro']and not data['unread']['binary_dep_dynamic']
 assert any('RUFF_COMMIT_HASH' in x for x in data['wrapped']['all_env_deps'])
 put(dest/'complete.json',{'status':0,'cases':list(data)})
