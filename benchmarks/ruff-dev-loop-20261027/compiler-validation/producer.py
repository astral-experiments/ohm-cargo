from pathlib import Path
import collections, hashlib, json, os, shutil, subprocess, sys, tempfile
n=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf');rt=n/'trait-pgo-state/sysroot';old=n/'trait-codegen-screen';root=Path(__file__).resolve().parent;repo=Path('/home/dev-user/code/oss/ruff-ohm-private-trait-20261026');base='93526150df078af7dd8fc4226cdcc469539d2001';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert not subprocess.check_output(['git','--no-optional-locks','-C',repo,'status','--porcelain']);assert subprocess.check_output(['git','-C',repo,'rev-parse','HEAD'],text=True).strip()==base
entry=next(p for p in (old/'receipts/objects-v2-0A').glob('compile.*.argv') if b'\0ruff_python_parser\0' in p.read_bytes());args=[s.decode() for s in entry.read_bytes().split(b'\0') if s];rmeta_rel=next((old/'seed').rglob('libruff_python_parser*.rmeta')).relative_to(old/'seed');assert '-Zpublic-api-hash' in args and '--emit=dep-info,metadata,link' in args and 'opt-level=1' in args
harness_sha=sha(entry)
def git(*args):return subprocess.check_output(['git','--no-optional-locks','-C',repo,*args]);
for rev in sys.argv[1:]:
 d=root/(rev+'-native');d.mkdir();cmd=['taskset','-c','20-23','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp'];sd=d/'fixtures';sd.mkdir();expanded=git('show','--format=','--binary',rev,'--','crates/ruff_python_parser/src');files=[l for l in git('diff','--name-only',rev+'^',rev,'--','crates/ruff_python_parser/src').decode().splitlines()];assert files
 for f in files:
  actual=repo/f;dst=sd/f;dst.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(actual,dst);cmd+=['--ro-bind',str(dst),str(actual)]
 subprocess.run(['git','apply','--reverse','-'],cwd=sd,input=expanded,check=True);(d/'rust-source.patch').write_bytes(expanded);(d/'original.rmeta').write_bytes((old/'seed'/rmeta_rel).read_bytes());
 with tempfile.TemporaryDirectory(dir=root) as t:
  store=Path(t);subprocess.run(['cp','-a','--reflink=auto',str(old/'seed')+'/.',store],check=True);cmd+=['--bind',str(store),str(old/'store'),'--chdir',str(repo),'--',*args];env=dict(os.environ,LD_LIBRARY_PATH=str(n/'trait-pgo-state/armA')+':'+str(rt/'lib'),RUSTUP_TOOLCHAIN='ohm',GIT_OPTIONAL_LOCKS='0')
  with (d/'stdout').open('wb') as o,(d/'stderr').open('wb') as e:r=subprocess.run(cmd,env=env,stdout=o,stderr=e)
  assert r.returncode==0,(rev,(d/'stderr').read_text()[-2000:]);shutil.copyfile(store/rmeta_rel,d/'modified.rmeta');(d/'status.json').write_text(json.dumps({'rev':rev,'base':base,'stage2_driver':sha(next((n/'trait-pgo-state/armA').glob('*.so'))),'compiler_argv_sha256':harness_sha,'source_files':files,'original_rmeta':sha(d/'original.rmeta'),'modified_rmeta':sha(d/'modified.rmeta')})+'\n');print(rev,'done',flush=True)
