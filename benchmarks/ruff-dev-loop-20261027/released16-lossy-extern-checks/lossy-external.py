"""Check duplicate displayed names using two genuine Rust externs selected over UTF-8 symlinks."""
import hashlib,json,os,sys,subprocess
from pathlib import Path
out=Path(sys.argv[1]);sdk=Path(sys.argv[2]);out.mkdir();ru=out/'rustup';(ru/'toolchains').mkdir(parents=True);(ru/'toolchains/ohm').symlink_to(sdk);env=dict(os.environ,RUSTUP_HOME=str(ru),RUSTC_BOOTSTRAP='1',PATH='/home/dev-user/.cargo/bin:'+os.environ['PATH']);env.pop('RUSTUP_TOOLCHAIN',None)
raw=bytes(out)+b'/lossy-\xff';valid=bytes(out)+'/lossy-\ufffd'.encode();os.mkdir(raw);os.mkdir(valid)
real=[v+b'/libsame.rlib' for v in [raw,valid]];links=[out/'libexternal_a.rlib',out/'libexternal_b.rlib'];sources=[out/'a.rs',out/'b.rs'];argv=[];res={}
def h(f):
 with open(f,'rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def run(phase,args,cwd=None):
 r=subprocess.run(['/home/dev-user/.cargo/bin/rustc','+ohm',*args],cwd=cwd or out,env=env,capture_output=True,timeout=60);argv.append([phase,[os.fsdecode(a) for a in args]]);(out/(phase+'.stderr')).write_bytes(r.stderr);return r
for i,n in enumerate(['external_a','external_b']):
 sources[i].write_text('pub fn value()->u32{'+str(17+12*i)+'}\n');rel=out/(n+'.rlib');r=run('compile-'+n,[sources[i],'--crate-name',n,'--crate-type=rlib','-o',rel]);assert r.returncode==0,r.stderr;os.rename(bytes(rel),real[i]);os.symlink(real[i],bytes(links[i]))
for order in [('a','b'),('b','a')]:
 tag=''.join(order);(out/'main.rs').write_text(''.join(f'extern crate external_{n};\n' for n in order)+'fn main(){println!("{} {}", external_a::value(),external_b::value());}');r=run(tag,['main.rs','--edition=2024','-Zbinary-dep-depinfo','-Zchecksum-hash-algorithm=sha256','--emit=link,dep-info='+tag+'.d','-o',tag,*sum((['--extern','external_'+n+'='+str(links['ab'.index(n)])] for n in order),[])]);fp=out/(tag+'.d');contents=fp.read_bytes() if fp.is_file() else b'';key=valid+b'/libsame.rlib';res[tag]={'returncode':r.returncode,'native':subprocess.check_output([out/tag],text=True).strip() if r.returncode==0 else None,'raw_input_sha':h(real[0]),'valid_input_sha':h(real[1]),'dep_rendered_count':contents.splitlines()[1].count(key) if contents else None,'matching_checksums':[l.decode('utf8',errors='backslashreplace') for l in contents.splitlines() if l.startswith(b'# checksum:') and key in l],'stderr':r.stderr.decode(errors='backslashreplace')[-1200:]}
# A non-Unicode real directory with an ASCII argv input is separate from explicit non-Unicode argv.
for mode in ['relative','absolute-invalid']:
 n=mode;wd=raw;open(wd+b'/test.rs','wb').write(b'pub fn value()->u32{17}\n');arg='test.rs' if n=='relative' else wd+b'/test.rs';r=run(n,[arg,'--crate-name','unicode_experiment','--crate-type=lib','-Zchecksum-hash-algorithm=sha256','--emit=metadata,dep-info='+str(out/(n+'.d'))],cwd=wd);res[n]={'returncode':r.returncode,'stderr':r.stderr.decode(errors='backslashreplace')[-1600:],'dep':(out/(n+'.d')).read_text() if (out/(n+'.d')).exists() else None}
(out/'actual-argv.json').write_text(json.dumps(argv,indent=2)+'\n');(out/'result.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res))
