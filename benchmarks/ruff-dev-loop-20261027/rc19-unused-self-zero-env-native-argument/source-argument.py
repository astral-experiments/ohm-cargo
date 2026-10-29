from pathlib import Path
import argparse,ast,hashlib,json,os,re,shutil,subprocess
NAME='native_input_env'
ORIGINAL=b'pub fn value() -> u32 { 1 }\n'; EDIT=ORIGINAL+b'pub struct AddedByNormalEdit;\n'
TEST=b'''#[link(name = "ohm_env_choice", kind = "static", modifiers = "-bundle")]
unsafe extern "C" { fn ohm_env_choice_value() -> i32; }
#[test]
fn reads_the_linked_archive() {
    println!("native-value={}", unsafe { ohm_env_choice_value() });
}
'''

def h(b):return hashlib.sha256(b).hexdigest()
def sha(p):
 with p.open('rb') as inp:return hashlib.file_digest(inp,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')

def test(s,tool,defaults=False):
 s.mkdir();src=s/'checkout';(src/'src').mkdir(parents=True);(src/'tests').mkdir();(src/'Cargo.toml').write_text('[package]\nname = "native_input_env"\nversion = "0.0.0"\nedition = "2024"\n');lib=src/'src/lib.rs';lib.write_bytes(ORIGINAL);(src/'tests/reader.rs').write_bytes(TEST)
 cache=s/'test-cache';cache.mkdir();prefix=['cargo','+ohm']+(['-Zohm-defaults=no'] if defaults else [])
 alias=s/'rustup/toolchains';alias.mkdir(parents=True);(alias/'ohm').symlink_to(tool, target_is_directory=True)
 early=s/'early';late=s/'late';early.mkdir();late.mkdir();store=s/'proof';store.mkdir();arc='libohm_env_choice.a';
 env={k:v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUSTUP_')) and k not in ('RUSTC','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER')}
 for var in ('LIBRARY_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LD_PRELOAD','LD_LIBRARY_PATH'):
  env.pop(var,None)
 env.update(RUSTUP_HOME=str(s/'rustup'),CARGO_HOME=str(cache),CARGO_NET_OFFLINE='true')
 for value in [17,29]:
  c=store/f'choice{value}.c';obj=store/f'choice{value}.o';a=store/f'choice{value}.a';c.write_text(f'int ohm_env_choice_value(void) {{ return {value}; }}\n');subprocess.run(['cc','-c',str(c),'-o',obj],check=True);subprocess.run(['ar','crs',a,obj],check=True)
 (src/'tests/reader.rs').write_text('#![feature(link_arg_attribute)]\n'+''.join(f'#[link(name="-L{directory}",kind="link-arg",modifiers="+verbatim")]\nunsafe extern "C" {{}}\n' for directory in [early,late])+TEST.decode());
 shutil.copyfile(store/'choice17.a',late/arc);assert not (early/arc).exists()
 results={}
 def run(label,state='trained'):
  report=s/label;report.mkdir();holder=s/state;target=holder/'target';shared=holder/'shared';resident=env|{'CARGO_TARGET_DIR':str(target),'CARGO_BUILD_BUILD_DIR':str(shared)};new=not holder.exists();args=prefix+['test','--offline','--no-run','-j2','--test','reader','--message-format=json'];command=['strace','-ff','-q','-s','262144','-e','trace=execve','-o',str(report/'exec'),*args]
  with (report/'cargo.stdout').open('wb') as out,(report/'cargo.stderr').open('wb') as er:got=subprocess.run(command,cwd=src,env=resident,stdout=out,stderr=er)
  rows=[json.loads(v) for v in (report/'cargo.stdout').read_bytes().splitlines()];arts=[x for x in rows if x['reason']=='compiler-artifact'];bins=[x for x in arts if x.get('executable') and x['target']['name']=='reader'];procs=[]
  assert not [x for x in rows if x['reason']=='build-script-executed']
  for trace in sorted(report.glob('exec.*')):
   for l in trace.read_text(errors='replace').splitlines():
    if not l.endswith('= 0') or not l.startswith('execve('):continue
    mt=re.search(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)',l)
    if mt is None:continue
    a=ast.literal_eval(mt[2]);p=Path(ast.literal_eval(mt[1]));n=p.name
    if n=='rustc' and '--crate-name' in a:
     procs.append({'pid':int(trace.name.split('.')[1]),'type':'rustc','crate':a[a.index('--crate-name')+1],'link_only':'link-only' in a or '-Zlink-only' in a,'run_sha':h(l.encode()),'exe':sha(p)})
    elif n in ('ld','ld.bfd','ld.lld','rust-lld') and '-o' in a and Path(a[a.index('-o')+1]).name.startswith('reader-'):
     all_l=[a[i+1] if v=='-L' else v[2:] for i,v in enumerate(a) if v.startswith('-L')];procs.append({'pid':int(trace.name.split('.')[1]),'type':'linker','native_name':n,'run_sha':h(l.encode()),'exe':sha(p),'early_ld_search':all_l.index(str(early)) if str(early) in all_l else None,'late_ld_search':all_l.index(str(late)) if str(late) in all_l else None,'has_choice_flag':any('ohm_env_choice' in v for v in a),'output':Path(a[a.index('-o')+1]).name})
  d={'status':got.returncode,'source':sha(lib),'build_scripts':0,'empty_at_start':new,'processes':procs,'typed':[(x['target']['name'],x['fresh']) for x in arts],'raw':{f.name:sha(f) for f in report.iterdir() if f.is_file()},'diagnostic':''};declared=(report/'cargo.stdout').read_text()+(report/'cargo.stderr').read_text()
  d['native_error']=any(z in declared.lower() for z in ('linking with','linking failed', 'linker script','file format not recognized','could not find native static library'))
  if bins:
   b,=bins;x=Path(b['executable']);assert x.is_file() and not x.is_symlink() and x.resolve().is_relative_to(holder);run=subprocess.run([str(x),'--exact','reads_the_linked_archive','--nocapture'],cwd=src,env=resident,capture_output=True);assert run.returncode==0 and b'1 passed' in run.stdout
   v,=re.findall(rb'native-value=(\d+)',run.stdout);(report/'test.stdout').write_bytes(run.stdout);d.update(value=int(v),file=str(x),elf=sha(x),test_sha=h(run.stdout));manifest=x.with_name(x.name+'.rlink-cache.json');d['unused_names']=json.loads(manifest.read_bytes()).get('unused_extern_names') if manifest.is_file() else None
  put(report/'result.json',d);results[label]=d;print(s.name,label,d['status'],d.get('value'),[(z['native_name'],z['early_ld_search'],z['late_ld_search'],z['has_choice_flag']) for z in procs if z['type']=='linker'],flush=True);return d
 first=run('01-first');assert first['status']==0 and first['value']==17,(first['status'],first['native_error']);primary=Path(first['file']);base=run('02-unchanged');assert base['value']==17
 tracked=early/arc;shutil.copyfile(store/'choice29.a',tracked);lib.write_bytes(EDIT)
 x=run('03-real-edit');assert x['status']==0 and x['value'] in (17,29);assert primary.is_file() and sha(primary)==x['elf'];primary.unlink();full=run('04-same-state-forced');assert full['value']==29
 clean=run('05-independent-empty-valid','empty-valid');assert clean['value']==29 and clean['empty_at_start']
 lib.write_bytes(ORIGINAL);tracked.write_bytes(b'OHM_INVALID_NATIVE_INPUT (\n');bad=run('06-real-restore-malformed');assert bad['status'] in (0,101)
 if primary.exists():assert primary.is_file() and not primary.is_symlink() and primary.resolve().is_relative_to(s/'trained');primary.unlink()
 fb=run('07-same-state-forced-malformed');assert fb['status']==101 and fb['native_error'];bc=run('08-independent-empty-malformed','empty-invalid');assert bc['status']==101 and bc['native_error'] and bc['empty_at_start']
 tracked.unlink();back=run('09-remove-and-recover');assert back['value']==17
 assert sha(late/arc)==sha(store/'choice17.a') and not tracked.exists()
 put(s/'terminal.json',dict(stages={n:{k:v for k,v in x.items() if k not in ('file','raw')} for n,x in results.items()},defaults_off=defaults,toolhash=sha(tool/'bin/cargo'),source_has_no_build_script=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Run nine genuine Cargo commands with two native directories passed by Rust source; no driver environment or build script.')
    parser.add_argument('sdk',type=Path);parser.add_argument('absent_directory',type=Path)
    parser.add_argument('--defaults-off',action='store_true');parser.add_argument('--expect',choices=['skip','relink'],required=True)
    args=parser.parse_args();empty=args.absent_directory.resolve();test(empty,args.sdk.resolve(strict=True),args.defaults_off)
    records=json.loads((empty/'terminal.json').read_text())['stages'];wanted=(17,0) if args.expect=='skip' else (29,101)
    assert (records['03-real-edit']['value'],records['06-real-restore-malformed']['status'])==wanted
