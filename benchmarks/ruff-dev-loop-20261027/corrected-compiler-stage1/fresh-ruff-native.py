from pathlib import Path
import hashlib,json,os,subprocess
d=Path(__file__).resolve().parent;score=Path('/mnt/devbox-scratch/dev-user/ohm-nonleaf-perflint-20261026/stage-score');rt=score/'sysroot';cargo=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf/cargo-native');arm=d/'stage-stable-expn-v7a';driver=next(arm.glob('*.so'));src=Path('/home/dev-user/code/oss/ruff-ohm-private-trait-20261026');fixture=d/'3ea20f6161-native/fixtures';root=Path('/dev/shm/ohm-rust-native-v7a-ruff-parser-20261027');root.mkdir();home=root/'cargo';home.mkdir();reg=Path('/home/dev-user/.cache/ohm-ruff-loop-20261026/registry-home/registry').resolve();(home/'registry').symlink_to(reg)
out=d/'same-epoch-ruff-v7a';out.mkdir();env=dict(os.environ,RUSTUP_HOME=str(score/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',CARGO_HOME=str(home),CARGO_TARGET_DIR=str(root/'target'),CARGO_BUILD_BUILD_DIR=str(root/'build'),CARGO_BUILD_JOBS='4',CARGO_NET_OFFLINE='true',CARGO_INCREMENTAL='1',RUSTC=str(rt/'bin/rustc'),LD_LIBRARY_PATH=str(rt/'lib'),GIT_OPTIONAL_LOCKS='0',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all')
env.pop('RUSTC_WRAPPER',None);env.pop('RUSTFLAGS',None)
ns=['taskset','-c','20-23','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(root),str(root),'--bind',str(out),str(out),'--ro-bind',str(cargo),str(rt/'bin/cargo'),'--ro-bind',str(driver),str(rt/'lib'/driver.name)]
fixfiles=[f for f in fixture.rglob('*') if f.is_file()]
def run(tag,edited):
 rec=out/tag;rec.mkdir();args=ns[:]
 if edited:
  for f in fixfiles:args+=['--ro-bind',str(f),str(src/f.relative_to(fixture))]
 args+=['--chdir',str(src),'--','/home/dev-user/.cargo/bin/cargo','+ohm','build','-p','ruff_python_parser','--offline','--locked','--message-format=json']
 with (rec/'stdout').open('wb') as so,(rec/'stderr').open('wb') as se:p=subprocess.run(args,env=env,stdout=so,stderr=se)
 if p.returncode: raise RuntimeError((p.returncode,(rec/'stderr').read_text()[-2200:]))
 rows=[j for l in (rec/'stdout').read_text().splitlines() if l.strip() and (j:=json.loads(l))['reason']=='compiler-artifact'];hs=[]
 for f in root.rglob('lib-ruff_python_parser.public-api-hash'):
  hs.append((str(f),json.loads(f.read_bytes())))
 dirty=[x['target']['name'] for x in rows if not x['fresh']];j={'units':len(rows),'dirty':dirty,'hashes':hs,'driver':hashlib.file_digest(driver.open('rb'),'sha256').hexdigest()};(rec/'result.json').write_text(json.dumps(j,indent=2)+'\n');print(tag,len(rows),dirty[-8:],hs,flush=True);return j
a=run('original',False);b=run('fresh',False);assert b['dirty']==[],b;c=run('modified',True);assert c['dirty']==['ruff_python_parser'],c;assert a['hashes']==c['hashes'] and len(a['hashes'])>=1,(a,c)
