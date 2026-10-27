"""Exercise two missing-input regressions without changing Cargo, rustc or Ruff."""
from pathlib import Path
import ast,fcntl,hashlib,json,os,re,shutil,subprocess,sys
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');d=p/'build-script-producer-reuse16-v1';work=d/'proof-boundary-v1';work.mkdir(exist_ok=False)
def h(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def put(f,v):f.parent.mkdir(parents=True,exist_ok=True);f.write_text(v)
def manifest(n,body=''):return '[package]\nname="'+n+'"\nversion="0.1.0"\nedition="2024"\n'+body
def active_script(case,num):
    suffix='println!("cargo::rerun-if-changed=watch'+str(num)+'.txt");'
    if case=='negative-module':
        logic=('std::fs::create_dir_all("src/item").unwrap(); std::fs::write("src/item/mod.rs","pub fn number()->i32 { 83 }\\n").unwrap();' if num==83 else 'let _=std::fs::remove_file("src/item/mod.rs");')
    else:
        logic='''let nd=std::fs::canonicalize("../native").unwrap();std::fs::write(nd.join("number.c"),"int native_value(void){return NUMBER;}").unwrap();
assert!(std::process::Command::new("cc").current_dir(&nd).args(["-c","number.c","-o","number.o"]).status().unwrap().success());
assert!(std::process::Command::new("ar").current_dir(&nd).args(["rcs","libshadowproof.a","number.o"]).status().unwrap().success());'''.replace('NUMBER',str(num))
    return 'fn main(){println!("cargo::rerun-if-changed=build.rs");'+suffix+logic+'}\n'
def fixture(case):
    w=work/case/'workspace';put(w/'Cargo.toml','[workspace]\nresolver="3"\nmembers=["bundle","app"'+(',"search"'if case!='negative-module'else '')+']\n')
    put(w/'bundle/Cargo.toml',manifest('probe_bundle','[dependencies]\nsearch={path="../search"}\n'if case!='negative-module'else ''))
    for i in (41,83):put(w/'bundle'/f'watch{i}.txt','unchanged\n')
    put(w/'app/Cargo.toml',manifest('probe_app','[dependencies]\nprobe_bundle={path="../bundle"}\n'))
    put(w/'app/src/main.rs','fn main(){println!("{}",probe_bundle::number());}\n')
    if case=='negative-module':
        put(w/'bundle/src/lib.rs','mod item; pub use item::number;\n')
        put(w/'bundle/src/item.rs','pub fn number()->i32{41}\n')
    else:
        (w/'native').mkdir()
        put(w/'bundle/src/lib.rs','#[link(name="shadowproof",kind="static")] unsafe extern "C"{fn native_value()->i32;} pub fn number()->i32{search::touch();unsafe{native_value()}}\n')
        put(w/'search/Cargo.toml',manifest('search'));put(w/'search/src/lib.rs','pub fn touch() {}\n')
        put(w/'search/build.rs','fn main(){println!("cargo::rerun-if-changed=build.rs");println!("cargo::rustc-link-search=native={}",std::fs::canonicalize("../native").unwrap().display());}\n')
    put(w/'bundle/build.rs',active_script(case,41));return w
def trace_process(q,td):
    result=[]
    for line in q.read_text(errors='replace').splitlines():
        m=re.match(r'\s*(\d+)\s+execve\("([^"]+)", (\[.*\]), [^\n]* = 0$',line)
        if not m:continue
        try:a=ast.literal_eval(m[3])
        except Exception:continue
        if '--crate-name' in a:
            result.append({'role':'rustc','crate':a[a.index('--crate-name')+1],'source':next((v for v in a if v.endswith('.rs')),None),'argv_sha256':hashlib.sha256(json.dumps(a,separators=(',',':')).encode()).hexdigest(),'native_paths':[v for n,v in enumerate(a) if n>0 and a[n-1]=='-L' and v.startswith('native=')],'native_flags':[v for n,v in enumerate(a) if n>0 and a[n-1]=='-l'],'linkonly':any(v in ['link-only','-Zlink-only'] for v in a),'direct_proc_macros':[v.split('=')[0] for n,v in enumerate(a) if n>0 and a[n-1]=='--extern' and v.endswith('.so')],'compiler_bytes':h(Path(m[2]))})
        elif m[2].endswith('/wild-ld/ld.bfd'):
            result.append({'role':'wild','basename':Path(a[a.index('-o')+1]).name if '-o' in a else '?'})
        elif '/run' in m[2] or m[2].endswith('/build-script-build'):
            if Path(m[2]).name.startswith(('build-script-build','build_script_build')):result.append({'role':'script','name':Path(m[2]).name})
    return result
def run(case,w,tag,mode,target):
    q=work/case/(mode+'-'+tag);q.mkdir()
    t=work/case/('store-'+target+'-'+mode);reg=d/'graph-registry';base=dict(HOME=str(Path.home()),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',RUSTUP_HOME=str(d/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(reg),CARGO_TARGET_DIR=str(t/'target'),CARGO_BUILD_BUILD_DIR=str(t/'shared'),CARGO_BUILD_JOBS='4',CARGO_NET_OFFLINE='true',GIT_OPTIONAL_LOCKS='0',LC_ALL='C.UTF-8')
    prog=['cargo','+ohm',mode,'--offline','--message-format=json','-p','probe_bundle' if mode=='check' else 'probe_app']+(['--no-run'] if mode=='test'else [])
    p0=subprocess.run(['strace','-f','-qq','-s','131072','-e','trace=execve','-o',str(q/'exec.log'),*prog],cwd=w,env=base,capture_output=True);(q/'stdout').write_bytes(p0.stdout);(q/'stderr').write_bytes(p0.stderr)
    rows=[json.loads(l) for l in p0.stdout.splitlines() if l.strip()]
    messages=[r['message'] for r in rows if r.get('reason')=='compiler-message'];arts=[r for r in rows if r.get('reason')=='compiler-artifact']
    s0=[r for r in rows if r.get('reason')=='build-script-executed' and 'probe_bundle' in r['package_id'] or r.get('reason')=='build-script-executed' and '/bundle#' in r['package_id']]
    assert len(s0)==1,(case,tag,s0,[(r['package_id'])for r in rows if r.get('reason')=='build-script-executed'])
    bs=s0[0];od=Path(bs['out_dir']);before={str(a.relative_to(w)):h(a)for a in [w/'bundle/src/lib.rs',w/'bundle/src/item.rs',w/'app/src/main.rs',w/'search/src/lib.rs'] if a.is_file()}
    deps=[];rustflags=[]
    for ar in arts:
        if ar['target']['name']=='probe_bundle' and 'lib' in ar['target']['kind']:
            for ff in ar['filenames']:
                v=Path(ff)
                for cand in v.parent.glob('probe_bundle*.d'):
                    lines=cand.read_text(errors='replace').splitlines();deps.append({'file':cand.name,'sha256':h(cand),'paths':[s for s in lines if s.startswith(('bundle/','src/'))], 'mentions_alternate':any('src/item/mod.rs' in s for s in lines),'mentions_archive':any('libshadowproof.a' in s for s in lines),'has_expected_main':any('src/lib.rs' in s for s in lines),'has_expected_item':any('src/item.rs' in s for s in lines)})
    kinds=trace_process(q/'exec.log',t);bundle_ar=next((Path(ff)for ar in arts if ar['target']['name']=='probe_bundle' for ff in ar['filenames'] if ff.endswith('.rlib')),None)
    a=w/'native/libshadowproof.a'
    native={'archive':h(a) if a.is_file() else None,'bundle_rlib':h(bundle_ar) if bundle_ar and bundle_ar.is_file() else None,'contains_native_object':('number.o' in subprocess.check_output(['ar','t',bundle_ar],text=True)) if bundle_ar and bundle_ar.is_file() else None}
    exe=next((Path(ar['executable'])for ar in arts if ar['target']['name']=='probe_app' and ar['executable'] and 'bin' in ar['target']['kind']),None);runtime=subprocess.check_output([exe],text=True).strip() if mode=='build' and exe and p0.returncode==0 else None
    result={'command':prog,'exit':p0.returncode,'runtime':runtime,'diagnostics':[{'code':(m.get('code')or{}).get('code'),'message':m['message'],'children':[ch['message'] for ch in m['children']]} for m in messages],'script':{k:bs[k] for k in ('linked_libs','linked_paths','cfgs','env')},'out_files':[str(a.relative_to(od)) for a in od.rglob('*') if a.is_file()],'existing_rust_source':before,'present_alternate':(w/'bundle/src/item/mod.rs').is_file(),'deps':deps,'native':native,'jobs':kinds,'raw_exec_sha':h(q/'exec.log'),'stdout_sha':h(q/'stdout'),'stderr_sha':h(q/'stderr')}
    (q/'result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');return result
def main():
    suite={}
    for case in ('negative-module','inherited-static'):
        w=fixture(case)
        for mode in (('check','build') if case=='negative-module' else ('build',)):
            z={}
            for tag,num,tar in [('prime',41,'warm'),('no-op',41,'warm'),('edit',83,'warm'),('empty-edit',83,'empty'),('restore',41,'warm')]:
                source=w/'bundle/build.rs';dat=active_script(case,num)
                if source.read_text()!=dat:source.write_text(dat)
                rec=run(case,w,tag,mode,tar)
                z[tag]=rec
                assert not rec['out_files'] and all(not v for v in rec['script'].values()),(case,mode,tag,rec['script'])
            suite[case+'-'+mode]=z
    (work/'suite.json').write_text(json.dumps(suite,sort_keys=True,indent=2)+'\n');print(json.dumps(suite))
with (p/'native-measure.lock').open('r') as f:
    fcntl.flock(f,fcntl.LOCK_EX);main()
