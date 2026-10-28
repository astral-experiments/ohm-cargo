"""Exercise return to a previously built native unit after a different Cargo feature selection occupied its CLI path."""
import ast, collections,hashlib,json,os,re,subprocess
from pathlib import Path
h=Path.home();d=Path('/run/user/1000/ohm-cli-switch-selected16-20261027-v2')/'small-proof';d.mkdir(); prev=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/build-script-producer-reuse16-v1')
w=d/'source';w.mkdir();s=d/'shared';s.mkdir();target=d/'target';target.mkdir()
def put(p,t):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t)
put(w/'Cargo.toml','[workspace]\nresolver="3"\nmembers=["used","tool","peer"]\n')
for n in ['used','tool','peer']:
    t=f'[package]\nname="{n}"\nversion="0.1.0"\nedition="2024"\n'
    if n=='used':t+='[features]\nother=[]\n'
    else:t+='[dependencies]\nused={path="../used"'+(', features=["other"]' if n=='peer'else '')+'}\n'
    put(w/n/'Cargo.toml',t)
    put(w/n/'src'/('lib.rs'if n=='used'else'main.rs'),'#[cfg(feature="other")] pub fn value() -> u32 {83}\n#[cfg(not(feature="other"))] pub fn value() -> u32 {41}\n'if n=='used'else'fn main() { println!("{}",used::value()); }\n')
e=dict(HOME=str(h),PATH=str(h/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',LC_ALL='C.UTF-8',RUSTUP_HOME=str(prev/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(d.parent/'reg'),CARGO_NET_OFFLINE='true',CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(s),CARGO_BUILD_JOBS='2',GIT_OPTIONAL_LOCKS='0')
H=lambda data:hashlib.sha256(data).hexdigest(); digest=lambda f:H(f.read_bytes())
ex=Path(subprocess.check_output(['rustup','which','--toolchain','ohm','cargo'],env=e,text=True).strip());assert digest(ex)=='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568'
subprocess.run(['cargo','+ohm','generate-lockfile','--offline'],cwd=w,env=e,check=True,capture_output=True)
products={}
events=[('pair','both',83),('single','single',41),('pair-return','both',83),('single-return','single',41),('single-repeat','single',41)]
for tag,choice,expected in events:
   rec=d/tag;rec.mkdir();select=['-p','tool','-p','peer','--bins']if choice=='both'else['-p','tool','--bin','tool']
   cmd=['cargo','+ohm','build','--locked','--offline','--message-format=json',*select]
   p=subprocess.run(['strace','-ff','-q','-s','32768','-e','trace=execve','-e','signal=none','-o',str(rec/'exec'),*cmd],cwd=w,env=e,capture_output=True)
   assert p.returncode==0,(tag,p.stderr[-400:]); (rec/'stdout').write_bytes(p.stdout);(rec/'stderr').write_bytes(p.stderr)
   rows=[json.loads(l)for l in p.stdout.splitlines()];arts=[z for z in rows if z['reason']=='compiler-artifact'];ef=target/'debug/tool';direct=subprocess.run([str(ef)],cwd=w,capture_output=True);assert direct.returncode==0
   jobs=[]
   for f in sorted(rec.glob('exec.*')):
      st=f.read_text(errors='replace')
      for l in st.splitlines():
         m=re.match(r'^execve\((".*?"), (\[.*\]), .* = 0$',l)
         if not m:continue
         path=ast.literal_eval(m[1]);a=ast.literal_eval(m[2]);nm=Path(path).name
         if nm=='rustc' and '--out-dir'in a:
            jobs.append(dict(role='link-only'if 'link-only'in a or '-Zlink-only'in a else 'full',crate=a[a.index('--crate-name')+1],argv_sha256=H(json.dumps(a,separators=(',',':')).encode()),pid=f.suffix[1:]))
         elif 'wild-ld/'in path:jobs.append(dict(role='wild',pid=f.suffix[1:],argv_sha256=H(json.dumps(a,separators=(',',':')).encode())))
   copies=[{'id':f.parent.parent.name,'sha256':digest(f),'same_inode_as_cli':f.samefile(ef)}for f in target.rglob('tool-*') if f.parent.name=='out'and f.is_file()and f.read_bytes()[:4]==b'\x7fELF']
   products[tag]=dict(choice=choice,expected_runtime=expected,actual_runtime=int(direct.stdout),output_sha256=digest(ef),fresh=sum(x['fresh']for x in arts),units=len(arts),jobs=jobs,stores=copies,command=cmd)
print(json.dumps(products,sort_keys=True))
