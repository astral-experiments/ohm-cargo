"""Exercise the two declaration orders and the unambiguous Unicode case on an installed release."""
import argparse,json,os,shutil,subprocess,tarfile
from pathlib import Path
a=argparse.ArgumentParser();a.add_argument('destination',type=Path);a.add_argument('--order',choices=('ab','ba','b'),required=True);o=a.parse_args();p=o.destination.resolve();p.mkdir();start=Path(__file__).resolve().parent
with tarfile.open(start/'observations.tar.gz') as t:
 for m in t.getmembers():
  prefix='input/heldout-fixture/'
  if not m.isfile() or not m.name.startswith(prefix):continue
  dest=p/'code'/m.name[len(prefix):];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(t.extractfile(m).read())
s=p/'code/hold_direct/src/main.rs';s.write_text(''.join('extern crate external_'+n+';\n' for n in o.order)+s.read_text()+'\nconst _: [(); 17] = [(); external_'+('a' if 'a' in o.order else 'b')+'::VALUE];\n'+('const _: usize = external_b::VALUE;\n' if 'a' in o.order else ''))
raw=os.fsdecode(os.fsencode(p)+b'/key-\xff');valid=str(p/'key-\ufffd');dirs=[Path(raw),Path(valid)];names=['external_a','external_b'];libs=[]
for d in dirs:d.mkdir()
env={**os.environ,'CARGO_HOME':str(p/'cargo-home'),'CARGO_TARGET_DIR':str(p/'target'),'CARGO_BUILD_BUILD_DIR':str(p/'shared'),'CARGO_BUILD_JOBS':'3'}
for k in ['RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTC','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST']:env.pop(k,None)
def rlib(i,v,out):
 f=p/'dep.rs';f.write_text(f'pub const VALUE:usize={v}; pub fn value()->u32{{{v}}}\n');tmp=p/'out.rlib';subprocess.run(['rustc','+ohm','--crate-name',names[i],f,'--crate-type','rlib','-Copt-level=1','-Cmetadata=kept-stable','-Cdebuginfo=0','-o',tmp],cwd=p,env=env,check=True);shutil.copy2(tmp,out)
for i,d in enumerate(dirs):
 out=d/'libsame.rlib';rlib(i,17 if i==0 or o.order=='b' else 39,out);alias=p/('lib'+names[i]+'.rlib');alias.symlink_to(out)
for name in o.order:
 i='ab'.index(name);libs+=['--extern',names[i]+'='+str(p/('lib'+names[i]+'.rlib'))]
changed=0 if 'a' in o.order else 1;rlib(changed,29,p/'next.rlib');env['CARGO_ENCODED_RUSTFLAGS']='\x1f'.join(libs);records={}
def check(label,env):
 cmd=['cargo','+ohm','check','--offline','-p','hold_direct','--message-format=json'];r=subprocess.run(cmd,cwd=p/'code',env=env,capture_output=True);(p/(label+'.stderr')).write_bytes(r.stderr);(p/(label+'.jsonl')).write_bytes(r.stdout);j=[json.loads(x) for x in r.stdout.splitlines()];root=[x for x in j if x.get('reason')=='compiler-artifact' and x['target']['name']=='hold_direct'];err=[x['message']['code']['code'] for x in j if x.get('reason')=='compiler-message' and x['message'].get('code')];records[label]={'exit':r.returncode,'fresh':root[0]['fresh'] if root else None,'diagnostics':err};return r
for phase in ['first','train','unchanged']:assert check(phase,env).returncode==0,phase
real=dirs[changed]/'libsame.rlib';stat=real.stat();buf=(p/'next.rlib').read_bytes();assert len(buf)==stat.st_size;real.write_bytes(buf);os.utime(real,ns=(stat.st_atime_ns,stat.st_mtime_ns));check('changed',env);check('empty',{**env,'CARGO_TARGET_DIR':str(p/'empty-target'),'CARGO_BUILD_BUILD_DIR':str(p/'empty-shared')});print(json.dumps(records,indent=2));assert records['empty']['exit']==101 and 'E0308' in records['empty']['diagnostics']
