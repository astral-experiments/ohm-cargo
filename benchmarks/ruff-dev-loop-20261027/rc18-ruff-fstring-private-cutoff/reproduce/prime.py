from pathlib import Path
import subprocess as sp, shutil, os, json, hashlib
Y=Path(os.environ['FSTRING_ROOT']).resolve();W=Y/'checkout';P=Y/'active';SDK=Path(os.environ['FSTRING_SDK']).resolve();RUSTUP=Path(os.environ['FSTRING_RUSTUP']).resolve();PROXY=Path(os.environ['FSTRING_PROXIES']).resolve(); RELEASE_CARGO='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573';H='1e9287d7654f1dbe4943d67ed5ac5363c9ee2161'; OLD='57d800be552a88751e7ecd06fc87b44714536033'; os.umask(0o077)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def env():
 e={k:v for k,v in os.environ.items() if not k.startswith(('RUSTFLAGS','RUSTC','CARGO_ENCODED_RUSTFLAGS','CARGO_UNSTABLE_OHM_','RUSTUP_HOME','CARGO_TARGET','CARGO_BUILD_BUILD_DIR'))}; return {**e,'RUSTUP_HOME':str(RUSTUP),'CARGO_HOME':str(P/'home'),'CARGO_TARGET_DIR':str(P/'target'),'CARGO_BUILD_BUILD_DIR':str(P/'shared'),'CARGO_NET_OFFLINE':'true','CARGO_BUILD_JOBS':'8','CARGO_TERM_COLOR':'never','RUST_BACKTRACE':'0'}
def write(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def phase(name):
 d=Y/'receipts'/name; d.mkdir(); assert shutil.disk_usage(Y).free>40*1024**3; args=[str(PROXY/'cargo'),'+ohm','build','--message-format=json'];rec={'cmd':args,'release_cargo':sha(SDK/'bin/cargo'),'source_head':sp.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip(),'modified':[x for x in sp.check_output(['git','diff','--name-only'],cwd=W,text=True).splitlines()],'source_files':{x:sha(W/x) for x in sp.check_output(['git','diff-tree','--no-commit-id','--name-only','-r',H],cwd=W,text=True).splitlines()},'affinity':sorted(os.sched_getaffinity(0)),'euid':os.geteuid()}; assert rec['release_cargo']==RELEASE_CARGO and rec['source_head']==H;write(d/'inputs.json',rec)
 with (d/'stdout.jsonl').open('xb') as out,(d/'stderr').open('xb') as err:
  run=sp.run(['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(d/'exec'),*args],env=env(),cwd=W,stdout=out,stderr=err)
 write(d/'exit.json',{'returncode':run.returncode}); assert run.returncode==0,(name,run.returncode)
def newstate():
 P.mkdir();(P/'target').mkdir();(P/'shared').mkdir();(P/'home').mkdir();shutil.copytree(Y/'registry-base/registry',P/'home/registry',symlinks=True);shutil.copyfile(Y/'registry-base/config.toml',P/'home/config.toml')
if __name__=='__main__':
 assert (Y/'setup-complete.json').is_file() and not P.exists();newstate();phase('cold-current')
