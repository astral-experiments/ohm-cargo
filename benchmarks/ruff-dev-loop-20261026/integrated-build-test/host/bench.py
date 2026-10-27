from pathlib import Path
import hashlib,os,shutil,stat,subprocess as sp,sys,json,time,signal,collections
R=Path(__file__).resolve().parent; spec=json.loads((R/'plan.json').read_text());S=Path('/mnt/devbox-scratch/dev-user');subject=spec['inputs'];old=Path('/home/dev-user/.cache/ohm-wild-regular-reloc-20261026');syscfg=json.loads((old/'final-inputs.json').read_text());basename='librustc_driver-774a793a844d5500.so'; rootcargo=Path('/home/dev-user/.cache/ohm-ruff-loop-20261026');binarydir=R/'wrappers';binarydir.mkdir(exist_ok=True)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def jswrite(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def git(src,*args,data=None):return sp.run(['git','--no-optional-locks','-C',src,*args],input=data,check=True,capture_output=True).stdout
def sh(p,text):
 if not p.exists() or p.read_text()!=text:p.write_text(text);p.chmod(0o755)
clang=Path('/usr/bin/clang');mode,arm,variant,label=sys.argv[1:5]; assert mode in ('build','test') and arm in subject and variant in ('original','edited');kind=sys.argv[5] if len(sys.argv)>5 else 'json';assert kind in ('json','plain','trace','count','preflight');p_dir=R/mode/label;p_dir.mkdir(parents=True,exist_ok=False);base=S/'ohm-highest-whole-20261026'/mode;st=S/'ohm-ruff-loop-20261026/wild-full'/('prebuilt-'+mode);active=st/'active';runtime=st/'runtime';src=Path('/home/dev-user/code/oss')/('ruff-ohm-wild-cli-count-20261026' if mode=='build' else 'ruff-ohm-wild-relocation-loop-20261026'); pin=git(src,'rev-parse','HEAD').decode().strip();assert pin==spec['ruff']; unit='ruff' if mode=='build' else 'fixtures'; rel='crates/ruff/src/main.rs' if mode=='build' else 'crates/ruff_python_formatter/tests/fixtures.rs';original=(src/rel).read_bytes();assert git(src,'show','HEAD:'+rel)==original,('external changed',rel)
patch=git(src,'show','da8ee78491','--format=','--',rel) if mode=='build' else (rootcargo/'entropy-corpus/test-target-discovery.patch').read_bytes();assert patch.count(b'diff --git')==(1 if mode=='build' else 2); fixture=(R/'fixtures'/mode/variant/rel);fixture.parent.mkdir(exist_ok=True,parents=True)
if not fixture.exists():
 fixture.write_bytes(original)
 if (mode=='build')==(variant=='original'):sp.run(['patch','--batch','-R','-p1','-i','/dev/stdin'],input=patch,cwd=R/'fixtures'/mode/variant,stdout=sp.DEVNULL,check=True)
 source_time=(src/rel).stat().st_mtime_ns;os.utime(fixture,ns=(source_time,source_time+(1_000_000_000 if variant=='edited' else 0)))
idx=Path(git(src,'rev-parse','--path-format=absolute','--git-path','index').decode().strip());idx0=sha(idx); cache=base/arm/'cargo-home';assert cache.is_dir(); cpu='0-3'; archive_config=next((base/'target').glob('debug/build/workspaces/*/v2-*/tikv-jemalloc-sys/*/out/build/config.log')); native_path=[line[6:] for line in archive_config.read_text(errors='replace').splitlines() if line.startswith('PATH: ')];assert native_path[0]==str(active/'cargo-home/bin');fixed_path=':'.join(native_path[1:]);pin_files={n:Path(d['path']) for n,d in subject[arm].items()}; drdir=Path('/home/dev-user/.cache/ohm-dynamorio-20261026');cargo=runtime/'bin/cargo';selected=st/'drivers/selected'; driver=selected/basename;linker=st/'ld.bfd';cmdname=st/'compiler-wrapper';wdir=binarydir/mode;wdir.mkdir(exist_ok=True)
# All actual rustc invocations receive the corresponding arm's driver. Metadata-only version queries retain their common binary identity.
sh(wdir/'compiler-wrapper',f'''#!/bin/sh
case " $* " in *" --crate-name ___ "*) exec "$@";; esac
case " $* " in
 *" --crate-name "*)
  printf '%s\\0' "$@" > "$RECEIPT/all-rustc.$$.argv"
  printf '%s\\n' "CARGO=$CARGO" "RUSTUP_TOOLCHAIN=$RUSTUP_TOOLCHAIN" "PATH=$PATH" "LD_LIBRARY_PATH=$LD_LIBRARY_PATH" "RUSTC=$RUSTC" > "$RECEIPT/env.$$"
  export LD_LIBRARY_PATH="{selected}${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"
  if test -n "${{OHM_HYBRID_OUT:-}}"; then
   unset OHM_COUNT_OUT
   exec valgrind --tool=cachegrind --cache-sim=no --branch-sim=no --trace-children=yes --verbose --vgdb=no "--cachegrind-out-file=$RECEIPT/guest.%p" "--log-file=$RECEIPT/vg.%p" "$@" --sysroot "{runtime}"
  fi
  exec "$@" --sysroot "{runtime}";;
esac
exec "$@"
''')
sh(wdir/'clang',f'#!/bin/sh\nexec /usr/bin/clang "$@" --ld-path={st}/wild-dispatch -Wl,--no-fork\n');sh(wdir/'wild-dispatch',f'#!/bin/sh\nexec {linker} "$@"\n');
# Preserve the stored Cargo executable path under its original Rustup dispatcher.
sh(wdir/'cargo',f'''#!/bin/sh
if test -n "${{OHM_HYBRID_OUT:-}}"; then
 printf '%s\\0' {cargo} "$@" > "$RECEIPT/cargo.$$.argv"
 exec {drdir}/sdk/bin64/drrun -no_follow_children -c {drdir}/client/libpidcounter.so "$RECEIPT/cargo.$$.ir" -- {cargo} "$@"
fi
exec {cargo} "$@"
''');
cmd=['taskset','-c',cpu,'bwrap','--tmpfs','/','--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--symlink','usr/bin','/bin','--symlink','usr/sbin','/sbin','--ro-bind','/etc','/etc','--ro-bind','/.cargo','/.cargo','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/home','--ro-bind','/home/dev-user','/home/dev-user','--bind',str(p_dir),str(p_dir),'--ro-bind',str(fixture),str(src/rel),'--dir','/mnt','--dir','/mnt/devbox-scratch','--dir',str(S),'--dir',str(st.parent.parent),'--dir',str(st.parent),'--dir',str(st),'--dir',str(active),'--dir',str(st/'drivers'),'--dir',str(selected),'--bind',str(base/'target'),str(active/'target'),'--bind',str(base/'shared'),str(active/'shared'),'--bind',str(cache),str(active/'cargo-home'),'--ro-bind',str(runtime),str(runtime),'--ro-bind',str(st/'rustup'),str(st/'rustup'),'--ro-bind',str(st/'dr-dispatch'),str(st/'dr-dispatch'),'--ro-bind',str(wdir/'cargo'),str(st/'dr-dispatch/bin/cargo'),'--ro-bind',str(pin_files['cargo']),str(cargo),'--ro-bind',str(pin_files['driver']),str(driver),'--ro-bind',str(pin_files['wild']),str(linker)]
for n in ('compiler-wrapper','clang','wild-dispatch'):cmd+=['--ro-bind',str(st/n if n in ('clang','wild-dispatch') else wdir/n),str(st/n)]
if mode=='test':
 second='crates/ruff_python_formatter/tests/snapshots/format@expression__nested_string_quote_style.py.snap';snapshot=(R/'fixtures'/mode/variant/second);assert snapshot.is_file();cmd+=['--ro-bind',str(snapshot),str(src/second)];
cmd+=['--chdir',str(src),'--'];env=dict(os.environ,CARGO=str(cargo),RUSTUP_HOME=str(st/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(active/'cargo-home'),CARGO_TARGET_DIR=str(active/'target'),CARGO_BUILD_BUILD_DIR=str(active/'shared'),CARGO_BUILD_JOBS='4',CARGO_TERM_COLOR='never',CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=str(st/'clang'),CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',RUSTC=str(runtime/'bin/rustc'),RUSTC_WRAPPER=str(cmdname),OHM_SYSROOT=str(runtime),OHM_PACKAGE=unit,GIT_OPTIONAL_LOCKS='0',LC_ALL='C.UTF-8',RECEIPT=str(p_dir),PATH=fixed_path,SSL_CERT_DIR='/etc/ssl/certs',SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt');assert not any(env.get(x) for x in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','OHM_COUNT_OUT','OHM_HYBRID_OUT'))
if kind=='preflight':cmd+=['/bin/sh','-c','id -u; stat -c "%a %u %n" / /mnt /mnt/devbox-scratch '+ ' '.join(str(p) for p in [S,st.parent.parent,st.parent,st,active,active/'cargo-home'])+'; sha256sum '+ ' '.join(str(p) for p in [cargo,runtime/'bin/rustc',driver,linker,fixture])+'; git --no-optional-locks rev-parse HEAD']
else:
 if kind=='trace':cmd+=['strace','-f','-s','1024','-e','trace=execve,execveat','-o',str(p_dir/'execve')]
 if kind=='count':env['OHM_HYBRID_OUT']=str(p_dir)
 cmd+=['/home/dev-user/.cargo/bin/cargo','+ohm',mode]+(['--no-run'] if mode=='test' else [])+['--locked','--offline']+(['--message-format=json'] if kind=='json' else [])
def inventory():
 ret={}
 for name in ('.ohm-registry-json-v1','.ohm-registry-json-v2','.ohm-git-index-sha1dc-v1'):
  q=cache/name
  if q.is_dir():ret[name]=sorted((p.name,p.stat().st_size,sha(p)) for p in q.iterdir() if p.is_file())
 return ret
free=shutil.disk_usage(S).free;assert free>24*(1<<30);ij=inventory();jswrite(p_dir/'start.json',{'arm':arm,'variant':variant,'kind':kind,'index':idx0,'inputs':{n:sha(p) for n,p in pin_files.items()},'patch':hashlib.sha256(patch).hexdigest(),'edited_file':sha(fixture),'mounted_source_hashes':{rel:sha(fixture),**({second:sha(snapshot)} if mode=='test' else {})},'scratch':free,'inventory':ij});start=time.monotonic_ns(); mapped={}
with (p_dir/'stdout').open('wb') as o,(p_dir/'stderr').open('wb') as e:
 proc=sp.Popen(cmd,env=env,stdout=o,stderr=e,start_new_session=True)
 while proc.poll() is None:
  for role,pat in [('cargo','cargo.*.argv'),('driver','all-rustc.*.argv')]:
   for f in p_dir.glob(pat):
    pid=f.name.split('.')[-2]; key=role+':'+pid
    if key in mapped:continue
    stat=pin_files[role].stat()
    try:maps=Path('/proc')/pid/'maps'; lines=maps.read_text().splitlines()
    except (OSError,ProcessLookupError):continue
    for l in lines:
     fields=l.split(maxsplit=5)
     if len(fields)<6:continue
     major,minor=(int(x,16) for x in fields[3].split(':'))
     if int(fields[4])==stat.st_ino and os.makedev(major,minor)==stat.st_dev:
      mapped[key]={'process':pid,'path':fields[5],'device':stat.st_dev,'inode':stat.st_ino,'sha256':subject[arm][role]['sha256']};break
  try:proc.wait(.09)
  except sp.TimeoutExpired:
   if shutil.disk_usage(S).free<24*(1<<30) or len(list(p_dir.glob('all-rustc.*.argv')))>2:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait();break
elapsed=time.monotonic_ns()-start;final=inventory();j={'returncode':proc.returncode,'elapsed_ns':elapsed,'inventory':final,'inv_equal':ij==final,'actual':[],'mapped':mapped,'idx_stable':idx0==sha(idx),'source_unchanged':original==(src/rel).read_bytes()};
if mode=='test':j['source_unchanged'] &= (src/second).read_bytes()==git(src,'show','HEAD:'+second)
for f in p_dir.glob('all-rustc.*.argv'):
 argv=f.read_bytes().split(b'\0');j['actual'].append(argv[argv.index(b'--crate-name')+1].decode());
if kind=='json' and proc.returncode==0:
 out={};graph=[];dirty=[]
 for line in (p_dir/'stdout').read_text().splitlines():
  a=json.loads(line);
  if a['reason']!='compiler-artifact':continue
  key=json.dumps([a['package_id'],a['target']['name'],a['target']['kind'],a['features'],a['profile']],separators=(',',':'),sort_keys=True);graph.append(key)
  if not a['fresh']:dirty.append(a['target']['name'])
  if a['executable']:
   real=base/'target'/Path(a['executable']).relative_to(active/'target');out[key]={'path':str(Path(a['executable']).relative_to(active/'target')),'bytes':real.stat().st_size,'sha256':sha(real)}
 j.update(graph=sorted(graph),dirty=dirty,outputs=out)
if kind in ('plain','trace','count') and proc.returncode==0:
 ref_name={'build':{'original':'native-parent-seven-lines','edited':'archive-native-saved-path'},'test':{'original':'native-parent-original','edited':'native-parent-edited'}}[mode][variant]; golden=json.loads((R/mode/ref_name/'result.json').read_text())['outputs']; verified={k:sha(base/'target'/v['path']) for k,v in golden.items()};j['elf_hashes']=verified;j['oracle']=ref_name;j['all_elf_equal']=all(verified[k]==g['sha256'] for k,g in golden.items());assert not (p_dir/'stdout').stat().st_size
jswrite(p_dir/'result.json',j);print(label,'rc',j['returncode'],'actual',j['actual'],'inventory',{k:len(v) for k,v in final.items()},'graph',len(j.get('graph',[])),'outputs',len(j.get('outputs',[])),'dirty',j.get('dirty',[]),flush=True);sys.exit(0 if proc.returncode==0 else 1)
