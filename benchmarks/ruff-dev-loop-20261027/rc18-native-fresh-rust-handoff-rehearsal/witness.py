"""Real unwrapped Rust frontend → GCC/collect2 → optional native-child QA protocol."""
from pathlib import Path
import ast,hashlib,json,os,re,shutil,subprocess,sys
root, label=Path(sys.argv[1]).resolve(),sys.argv[2];assert label.isalnum()
d=root/label;d.mkdir(mode=0o700);src=d/'source';reports=d/'reports';reports.mkdir();external=d/'external';external.mkdir()
h=lambda b:hashlib.sha256(b).hexdigest()
def fhash(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,s):
 p.parent.mkdir(exist_ok=True,parents=True);p.write_text(s)
def dump(p,j):p.write_text(json.dumps(j,sort_keys=True,indent=2)+'\n')
write(src/'Cargo.toml','[workspace]\nmembers=["tokens","observer","leaf","search","reader"]\nresolver="3"\n[profile.dev.package.leaf]\nincremental=false\n')
crates={'tokens':'','observer':'[lib]\nproc-macro=true\n','leaf':'[dependencies]\ntokens={path="../tokens"}\nobserver={path="../observer"}\n','search':'','reader':'[dependencies]\nleaf={path="../leaf"}\nsearch={path="../search"}\n[[test]]\nname="reader_case"\npath="tests/reader.rs"\nharness=false\n'}
for n,rest in crates.items():write(src/n/'Cargo.toml',f'[package]\nname="{n}"\nversion="0.1.0"\nedition="2021"\n'+rest)
write(src/'tokens/src/lib.rs','#[macro_export] macro_rules! observed { () => { ::observer::observe!(foreign_token) }; }\n')
write(src/'observer/src/lib.rs','extern crate proc_macro;use proc_macro::TokenStream;#[proc_macro] pub fn observe(t:TokenStream)->TokenStream{let s=t.into_iter().next().unwrap().span();::std::hint::black_box(format!("{s:?}"));"()".parse().unwrap()}\n')
write(src/'leaf/src/lib.rs','const _: () = tokens::observed!();\n#[inline(never)] pub fn answer()->i32{0}\n')
write(src/'search/build.rs','''use std::path::PathBuf;
fn main(){let inp=PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").unwrap()).parent().unwrap().parent().unwrap().join("external/libutil.a");let out=PathBuf::from(std::env::var_os("OUT_DIR").unwrap());if inp.is_file(){std::fs::copy(inp,out.join("libutil.a")).unwrap();}println!("cargo:rerun-if-changed=build.rs");println!("cargo:rustc-link-search=native={}",out.display());}
''')
write(src/'search/src/lib.rs','unsafe extern "C" {fn atoi(p:*const i8)->i32;} #[inline(never)] pub fn number()->i32{unsafe{atoi(std::hint::black_box(c"41").as_ptr())}}\n')
write(src/'reader/src/lib.rs','pub fn ordinary_library() {}\n')
write(src/'reader/tests/reader.rs','fn main(){println!("native-value={}",leaf::answer()+search::number());}\n')
env={k:v for k,v in os.environ.items() if not k.startswith('CARGO_') and k not in ('RUSTFLAGS','RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUST_BACKTRACE')}
env.update(CARGO_HOME=str(d/'cargo-home'),CARGO_TARGET_DIR=str(d/'target'),CARGO_BUILD_BUILD_DIR=str(d/'shared'),CARGO_NET_OFFLINE='true',OHM_QA_NATIVE_STATE=str(d))
cargo=[str(Path.home()/'.cargo/bin/cargo'),'+ohm']
def run(argv,environment=env):
 return subprocess.run(list(map(str,argv)),env=environment,cwd=src,capture_output=True,timeout=110)
run(cargo+['generate-lockfile','--offline']).check_returncode()
cmd=cargo+['test','--no-run','-p','reader','--test','reader_case','--locked','--offline','-j1','--message-format=json']
records={};outdir=None;casebin=None
def phase(name,wanted):
 global outdir,casebin
 dest=reports/name;dest.mkdir(); cenv=env|{'OHM_QA_NATIVE_PHASE':name}
 full=['strace','-f','-qq','-s','131072','-e','trace=execve','-o',str(dest/'trace.private'),'--',*cmd]
 cp=run(full,cenv);(dest/'stdout').write_bytes(cp.stdout);(dest/'stderr').write_bytes(cp.stderr)
 procs=[]
 for ln in (dest/'trace.private').read_text(errors='replace').splitlines():
  m=re.match(r'^(\d+)\s+execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[^ ]+ )?/\* [0-9]+ vars \*/\)\s+= 0$',ln)
  if not m:continue
  path=ast.literal_eval(m[2]);args=ast.literal_eval(m[3]);n=Path(path).name
  zs={x[2:] for x in args if x.startswith('-Z') and len(x)>2}|{b for a,b in zip(args,args[1:]) if a=='-Z'}
  if n=='rustc' and '--crate-name' in args:
   unit=args[args.index('--crate-name')+1];kind='link-only' if 'link-only' in zs else 'full'
   if unit=='___':continue
  elif n=='collect2':unit=None;kind='collect2'
  elif n in ('cc','gcc'):unit=None;kind='cc'
  elif path==env['OHM_QA_NATIVE_STOCK']:unit=None;kind='stock'
  elif n=='ld.bfd':unit=None;kind='handoff'
  else:continue
  procs.append({'pid':int(m[1]),'exe':path,'argv':args,'unit':unit,'kind':kind,'original_line_sha256':h(ln.encode())})
 rows=[json.loads(x.read_bytes()) for x in sorted((d/'launches'/name).glob('*.json'))];assert len(rows)==1,(name,len(rows),cp.stderr.decode()[-1200:])
 rr=rows[0];msgs=[json.loads(l) for l in cp.stdout.splitlines()]
 for v in msgs:
  if v.get('reason')=='build-script-executed' and 'search' in v['package_id']:outdir=Path(v['out_dir'])
  if v.get('reason')=='compiler-artifact' and v['target']['name']=='reader_case' and v.get('executable'):casebin=Path(v['executable'])
 sel=dict(phase=name,command=cmd,status=cp.returncode,actual_processes=procs,shim=rr,diagnostic=cp.stderr.decode(errors='replace'),
          ru_rows=[[r['unit'],r['kind']] for r in procs if r['unit']],stock=sum(r['kind']=='stock' for r in procs),
          output_after_outer=os.path.lexists(rr['output']) and fhash(Path(rr['output'])),uid=os.geteuid(),
          cargo_reported=next((m['fresh'] for m in msgs if m.get('reason')=='compiler-artifact' and m['target']['name']=='reader_case'),None))
 if wanted is not None:
  assert cp.returncode==0,(name,cp.stderr); val=run([casebin]);assert val.returncode==0
  sel.update(app=val.stdout.decode().strip(),final_file=fhash(casebin))
  assert sel['app']==f'native-value={wanted}',(name,sel['app'])
 else:assert cp.returncode and 'error' in cp.stderr.decode(errors='replace').lower(),(name,cp.returncode,cp.stderr)
 records[name]=sel;dump(dest/'structured.json',sel);dump(reports/'all.json',records)
 print(name,sel['status'],sel.get('app'),sel['stock'],sel['ru_rows'],rr['decision'],rr['key_error'],rr['before'],rr['after'],flush=True)
 return sel
def gold(name,value):
 for n in ['target','shared']:(d/n).rename(d/(n+'-saved'))
 try:return phase(name+'gold',value)
 finally:
  for n in ['target','shared']:
   (d/n).rename(d/(n+'-'+name+'gold'));(d/(n+'-saved')).rename(d/n)
def archive(value):
 c=external/'native.c';o=external/'native.o';a=external/'libutil.a';write(c,f'int atoi(const char*s){{return {value};}}\n');run(['cc','-fPIC','-c',c,'-o',o]).check_returncode();run(['ar','rcsD',a,o]).check_returncode();shutil.copyfile(a,outdir/'libutil.a')
phase('cold',41);phase('train',41);pos=phase('repeat',41)
archive(83);neg=phase('higher',83);g=gold('higher',83)
assert neg['final_file']==g['final_file']
(outdir/'libutil.a').write_bytes(b'INPUT ( ( deliberately-invalid )\n');(external/'libutil.a').write_bytes((outdir/'libutil.a').read_bytes());bad=phase('malformed',None)
(outdir/'libutil.a').unlink();(external/'libutil.a').unlink();rc=phase('restored',41);g=gold('restored',41)
assert rc['final_file']==g['final_file']
assert pos['stock']==0 and pos['shim']['decision']=='fixture-native-fresh' and pos['shim']['before']==pos['shim']['after']
assert any([u,k]==['reader_case','link-only'] for u,k in pos['ru_rows']) and not pos['cargo_reported']
assert neg['shim']['decision']==bad['shim']['decision']=='real-stock' and neg['stock']>=1 and bad['stock']>=1
assert pos['shim']['parent_exe'].endswith('/collect2') and pos['uid']==1000 and pos['shim']['arch']=='x86_64'
dump(reports/'qualified.json',{'pass':True,'tested':sorted(records),'fresh_candidate':pos['shim']['key'],'release_lineage':'R2 source-qualified rehearsal unless host binding states installed -18','scope':'restricted five-crate controls demonstrate the outer protocol; settled host and inactive plugin are fixture assumptions, not general completeness'})
