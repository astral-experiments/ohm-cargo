import argparse,ast,importlib.util,json,os,re,shutil,subprocess
from pathlib import Path
q=Path(__file__).with_name('source-argument.py');sp=importlib.util.spec_from_file_location('base',q);base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
parser=argparse.ArgumentParser();parser.add_argument('sdk',type=Path);parser.add_argument('empty_path',type=Path);parser.add_argument('--defaults-off',action='store_true');args=parser.parse_args();TOOL=args.sdk.resolve(strict=True);root=args.empty_path.resolve();root.mkdir()
def plain(off):
 case=root/('default-dirs-off' if off else 'default-dirs-on');case.mkdir();source=case/'checkout';(source/'src').mkdir(parents=True);(source/'tests').mkdir();(source/'Cargo.toml').write_text('[package]\nname="native_input_env"\nversion="0.0.0"\nedition="2024"\n');(source/'src/lib.rs').write_bytes(base.ORIGINAL);(source/'tests/reader.rs').write_bytes(base.TEST)
 native=case/'libchoice.a';c=case/'choice.c';c.write_text('int ohm_env_choice_value(void) { return 17; }\n');subprocess.run(['cc','-c',c,'-o',case/'choice.o'],check=True);subprocess.run(['ar','crs',native,case/'choice.o'],check=True);tc=case/'rustup/toolchains';tc.mkdir(parents=True);(tc/'ohm').symlink_to(TOOL,target_is_directory=True);(case/'home').mkdir()
 env={k:v for k,v in os.environ.items() if not k.startswith(('CARGO_','RUSTUP_')) and k not in ['LIBRARY_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LD_PRELOAD','LD_LIBRARY_PATH','RUSTC','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER']};env.update(RUSTUP_HOME=str(case/'rustup'),CARGO_HOME=str(case/'home'),CARGO_TARGET_DIR=str(case/'target'),CARGO_BUILD_BUILD_DIR=str(case/'shared'),CARGO_NET_OFFLINE='true')
 def run(label):
  d=case/label;d.mkdir();prefix=['cargo','+ohm']+(['-Zohm-defaults=no'] if off else []);argv=['strace','-ff','-q','-s','262144','-o',str(d/'exec'),'-e','trace=execve',*prefix,'test','--offline','--no-run','-j2','--test','reader','--message-format=json'];
  with (d/'cargo.stdout').open('wb') as out,(d/'cargo.stderr').open('wb') as err:result=subprocess.run(argv,env=env,cwd=source,stdout=out,stderr=err)
  rows=[json.loads(l) for l in (d/'cargo.stdout').read_bytes().splitlines()];assert not [a for a in rows if a['reason']=='build-script-executed'];rr=[];ll=[]
  for trace in d.glob('exec.*'):
   for line in trace.read_text().splitlines():
    if not line.startswith('execve(') or not line.endswith('= 0'):continue
    item=re.search(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)',line);a=ast.literal_eval(item[2]);name=Path(ast.literal_eval(item[1]));dirs=[a[i+1] if v=='-L' else v[2:] for i,v in enumerate(a) if v.startswith('-L')]
    if name.name=='rustc' and '--crate-name' in a and a[a.index('--crate-name')+1]=='reader':rr.append((dirs,base.h(line.encode())))
    if name.name in ('ld','ld.bfd','ld.lld','rust-lld') and '-o' in a and Path(a[a.index('-o')+1]).name.startswith('reader-'):
     assert any('ohm_env_choice' in v for v in a);ll.append((dirs,base.h(line.encode()),base.sha(name)))
  assert rr and ll and result.returncode==101 and 'ohm_env_choice' in (d/'cargo.stdout').read_text();return {'status':result.returncode,'rustc_args':rr,'linker_args':ll,'raw':{f.name:base.sha(f) for f in d.iterdir() if f.is_file()},'build_scripts':0}
 first=run('01-native-absent');directories={case/'target/debug/deps'}|{Path(v.split('=',1)[1]) for dirs,raw in first['rustc_args'] for v in dirs if v.startswith('dependency=')};assert len(directories)>=2 and all(d.resolve().is_relative_to(case) for d in directories)
 for directory in directories:
  directory.mkdir(parents=True,exist_ok=True);dest=directory/'libohm_env_choice.a';assert not dest.exists() and not dest.is_symlink();shutil.copyfile(native,dest);assert base.sha(native)==base.sha(dest)
 (source/'src/lib.rs').write_bytes(base.EDIT);second=run('02-real-edit-two-private-rust-dirs');assert not any(Path(a).resolve() in directories for dirs,hash_,elf in second['linker_args'] for a in dirs)
 base.put(case/'terminal.json',{'first':first,'second':second,'sources':[base.h(base.ORIGINAL),base.h(base.EDIT)],'archives':{str(d.relative_to(case)):base.sha(d/'libohm_env_choice.a') for d in directories},'all_native_absent_from_actual_L':True,'defaults_off':off})
 print(case.name,second['status'],'present directories',len(directories),'actual ld cmds',len(second['linker_args']),flush=True)

plain(args.defaults_off)
