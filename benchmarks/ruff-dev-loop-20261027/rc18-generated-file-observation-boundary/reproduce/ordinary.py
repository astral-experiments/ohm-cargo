"""Profile the official Cargo, preserving the ordinary command's 182 fully fresh artifacts."""
import hashlib, json, os, pathlib, subprocess, time
H=pathlib.Path.home()
B=H/".cache/ohm-ty-vendored-watch-20261028-v1"; P=H/".cache/ohm-ty-vendored-script-consumer-20261028-v1"/"warm"
O=H/".cache/ohm-ruff-18-fresh-prep-linkscout-20261028"
SDK=H/".cache/ohm-ron-producer-freshness-20261028/official-sdk"; V=O/"tools"
D=O/"logs/ordinary-secured-v1";D.mkdir()
def sha(p):
 with p.open('rb')as fp:return hashlib.file_digest(fp,'sha256').hexdigest()
S=json.loads((O/'status.json').read_text()); assert S['terminal'];want=S['commands'][-1]['products']
ns=['bwrap','--die-with-parent','--tmpfs','/','--dir','/.cargo','--ro-bind','/.cargo/config.toml','/.cargo/config.toml','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--ro-bind','/etc','/etc','--ro-bind','/sys','/sys','--dir','/home','--ro-bind',str(H),str(H),'--ro-bind','/mnt','/mnt','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(P/'checkout'),str(B/'checkout'),'--bind',str(D),str(D)]
for n in ('target','shared','home'):ns+=['--bind',str(O/n),str(B/n)]
ns+=['--chdir',str(B/'checkout'),'--','taskset','-c','0-7']
env={k:v for k,v in os.environ.items()if not k.startswith(('CARGO_','RUSTC_','RUSTUP_')) and k not in ['RUSTFLAGS','RUSTDOCFLAGS','RUSTC','RUSTDOC','CARGO_LOG']}
env.update(RUSTUP_HOME=str(SDK.parent/'official-installer-state/rustup'),CARGO_HOME=str(B/'home'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='8',CARGO_BUILD_BUILD_DIR=str(B/'shared'),CARGO_TARGET_DIR=str(B/'target'),GIT_OPTIONAL_LOCKS='0')
ownership=subprocess.check_output([*ns,"/usr/bin/stat","-c","%n %u %a","/","/home",str(H),str(B/"home")],text=True);print("private-namespace",ownership,flush=True);assert all(row.split()[-2] in ("0","1000") for row in ownership.splitlines())
args=[str(H/'.cargo/bin/cargo'),'+ohm','build','--locked','--offline','-p','ty_vendored']
out={'environment':{'affinity':'0-7','load_start':pathlib.Path('/proc/loadavg').read_text().split()[:3]},'commands':[]}
def invoke(label,prefix):
 with (D/(label+".out")).open("wb")as o,(D/(label+".err")).open("wb")as e:
  start=time.perf_counter_ns();cp=subprocess.run([*ns,*prefix,*args],env=env,stdout=o,stderr=e);v=time.perf_counter_ns()-start
 assert cp.returncode==0 and (D/(label+".out")).stat().st_size==0
 assert all(sha(O/'target'/pathlib.Path(k).relative_to(B/'target'))==h for k,h in want.items());err=(D/(label+".err")).read_text();assert "Compiling " not in err and "Finished "in err
 out['commands'].append({'label':label,'ns':v if not prefix else None,'stdout':sha(D/(label+".out")),'stderr':sha(D/(label+".err"))})
for n in range(7):invoke("plain"+str(n),[])
for idx in (1,2):
 name='fs'+str(idx);d=D/name;d.mkdir()
 invoke(name,["strace","-ff","-qq","-yy","-s","0","-T","-e","trace=%file,read,pread64,getdents64,write,fchmod,clone,clone3,close","-o",str(d/"trace")])
assert len(want)==2
out["program_artefacts"]=want
(D/'elapsed.json').write_text(json.dumps(out,indent=2));print("ordinary",json.dumps(out),flush=True)
env.update(SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/etc/ssl/certs',VALGRIND_LIB=str(V/'usr/libexec/valgrind'))
v=[str(V/'usr/bin/valgrind.bin'),'--tool=callgrind','--quiet','--cache-sim=no','--collect-jumps=no','--trace-children=yes','--compress-strings=yes','--callgrind-out-file='+str(D/'callgrind.%p'),'--log-file='+str(D/'valgrind.%p')]
invoke('instructions',v)
print('accepted',[(f.name,f.stat().st_size)for f in D.glob('callgrind.*')],flush=True)
