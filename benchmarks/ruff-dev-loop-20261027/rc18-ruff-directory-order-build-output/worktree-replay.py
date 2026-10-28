"""Run ordinary released Cargo on a real copy-on-write donor and compare its recipient to a same-path empty build."""
from pathlib import Path
import fcntl,hashlib,json,os,stat,subprocess,sys
import argparse,shutil
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work-root',type=Path,required=True,help='New private source and result directory')
parser.add_argument('--other-source-root',type=Path,required=True,help='New directory on another source filesystem')
parser.add_argument('--cow-root',type=Path,required=True,help='New directory on a reflink-capable filesystem')
parser.add_argument('--rustup-home',type=Path,required=True,help='Rustup home with a private ohm alias for official 1.99.0-18')
parser.add_argument("--cargo-shim",type=Path,help="Optional absolute Rustup Cargo proxy")
args=parser.parse_args()
base=args.work_root.resolve();other=args.other_source_root.resolve();cow=args.cow_root.resolve()
for dr in (base,other,cow):dr.mkdir(mode=0o700)
shim=(args.cargo_shim or Path(shutil.which('cargo'))).absolute()
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(n,d): (base/n).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
assert os.geteuid()==os.getuid()!=0 and Path('/').stat().st_uid==0
assert list(map(int,Path('/proc/self/uid_map').read_text().split()))==[0,0,4294967295]
assert sha(args.rustup_home/'toolchains/ohm/bin/cargo')=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573'
src=cow/'clone-fixture';to=cow/'clone-output';src.write_bytes(b'cow source proof')
with src.open('rb') as a,to.open('xb') as b:fcntl.ioctl(b.fileno(),0x40049409,a.fileno())
assert to.read_bytes()==src.read_bytes();to.write_bytes(b'distinct');assert src.read_bytes()==b'cow source proof'
result={}
def git(cwd,*argv,env=None):return subprocess.check_output(['git',*argv],cwd=cwd,env=env)
build_rs=r'''use std::{env,fs,path::Path};
fn main(){
    let chosen=fs::read_dir("data").unwrap().map(|x|x.unwrap().file_name().into_string().unwrap()).collect::<Vec<_>>().join(",");
    fs::write(Path::new(&env::var_os("OUT_DIR").unwrap()).join("answer.txt"),chosen).unwrap();
}
'''
for case in ('ordinary','equal-times'):
 w=base/case;w.mkdir();fsroot=cow/case;fsroot.mkdir();donor=w/'source';donor.mkdir();dest=other/case
 (donor/'src').mkdir();(donor/'data').mkdir();(donor/'Cargo.toml').write_text('[package]\nname="order_probe"\nversion="0.1.0"\nedition="2024"\n');(donor/'build.rs').write_text(build_rs);(donor/'src/main.rs').write_text('fn main(){println!("{}",include_str!(concat!(env!("OUT_DIR"),"/answer.txt")));}\n')
 for n in range(32,-1,-1):(donor/'data'/f'entry-{n:02}').write_text(f'entry {n}\n')
 (donor/'.gitignore').write_text('/target\n')
 for n in ('home','registry','tmp','logs'):(w/n).mkdir()
 shared=fsroot/'shared';shared.mkdir();donor_target=fsroot/'donor-output';recipient_target=fsroot/'recipient-output'
 env={'PATH':str(shim.parent)+':/usr/local/bin:/usr/bin:/bin','HOME':str(w/'home'),'RUSTUP_HOME':str(args.rustup_home),'RUSTUP_TOOLCHAIN':'ohm','RUSTUP_AUTO_INSTALL':'0','CARGO_HOME':str(w/'registry'),'CARGO_NET_OFFLINE':'true','CARGO_BUILD_BUILD_DIR':str(shared),'CARGO_BUILD_JOBS':'2','CARGO_PROFILE_DEV_DEBUG':'0','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','TMPDIR':str(w/'tmp')}
 prefix=[str(shim),'+ohm']
 def command(label,where,tar,argv):
  e=dict(env,CARGO_TARGET_DIR=str(tar));logs=w/'logs';tr=logs/(label+'.trace')
  run=subprocess.run(['strace','-qq','-f','-s','1024','-e','trace=execve','-o',str(tr),*prefix,*argv],cwd=where,env=e,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  (logs/(label+'.stdout')).write_bytes(run.stdout);(logs/(label+'.stderr')).write_bytes(run.stderr);assert run.returncode==0,(case,label,run.stderr[-1500:])
  return run,tr
 command('lock',donor,donor_target,['generate-lockfile','--offline'])
 git(donor,'init','-q','-b','main',env=env);git(donor,'add','.',env=env);git(donor,'-c','user.name=Worktree Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture',env=env)
 tracked=git(donor,'ls-files','-z',env=env).decode().strip('\0').split('\0')
 canonical_time=1792012558000000000
 if case=='equal-times':
  for n in tracked:os.utime(donor/n,ns=(canonical_time,canonical_time))
 def settings(s):return {n:[sha(s/n), (s/n).stat().st_mtime_ns] for n in tracked}
 def snapshot(label,where,tar):
  run,tr=command(label,where,tar,['build','--locked','--offline','--message-format=json']);rows=[json.loads(z) for z in run.stdout.splitlines()]
  assert rows[-1]=={'reason':'build-finished','success':True}
  arts=[r for r in rows if r['reason']=='compiler-artifact'];progs=[Path(r['executable']) for r in arts if r['target']['kind']==['bin'] and r.get('executable')];assert len(progs)==1
  program=progs[0];observed=subprocess.check_output([program],cwd=where,env=env,text=True).strip().split(',');natural=os.listdir(where/'data');assert sorted(natural)==sorted(observed)
  traced=[l for l in tr.read_text().splitlines() if l.endswith(' = 0')];scripts=[l for l in traced if 'execve("' in l and l.split('execve("',1)[1].split('"',1)[0].endswith(('/build-script-build','/out/build_script_build'))]
  rec={'source_order':natural,'native_output':observed,'cargo_rc':run.returncode,'compiler_messages':[[r['target']['name'],r['fresh']] for r in arts],'actual_script_execs':len(scripts),'elf_sha256':sha(program),'trace':sha(tr),'stdout':hashlib.sha256(run.stdout).hexdigest(),'stderr':hashlib.sha256(run.stderr).hexdigest()}
  return rec
 rec={};rec['donor']=snapshot('donor-build',donor,donor_target);rec['donor-repeat']=snapshot('donor-repeat',donor,donor_target)
 wr,tr=command('worktree-add',donor,donor_target,['worktree','add','-b','recipient',str(dest),'HEAD','--target-dir',str(recipient_target)])
 lines=[l.strip().replace(str(dest),'$RECIPIENT').replace(str(recipient_target),'$RECIPIENT_TARGET') for l in wr.stderr.decode().splitlines() if 'Seeded ' in l or 'Skipped ' in l or 'Target ' in l]
 rec['worktree']={'messages':lines,'stdout':hashlib.sha256(wr.stdout).hexdigest(),'stderr':hashlib.sha256(wr.stderr).hexdigest(),'trace':sha(tr),'git_worktrees':git(donor,'worktree','list','--porcelain',env=env).count(b'worktree '),'reflink_supported':True}
 assert rec['worktree']['git_worktrees']==2
 rec['worktree']['seeded']=any(x.startswith('Seeded ') for x in lines)
 if case=='equal-times':
  for n in tracked:os.utime(dest/n,ns=(canonical_time,canonical_time))
 A,B=settings(donor),settings(dest);assert all(A[n][0]==B[n][0] for n in tracked) and (A==B or case=='ordinary');assert not git(dest,'status','--porcelain',env=env)
 rec['same_tracked_mtimes']=sum(A[n]==B[n] for n in A);rec['tracker_count']=len(tracked);rec['same_bytes']=True
 rec['recipient']=snapshot('recipient-build',dest,recipient_target);rec['recipient-repeat']=snapshot('recipient-repeat',dest,recipient_target)
 recipient_target.rename(fsroot/'retained-target');shared.rename(fsroot/'retained-shared');shared.mkdir()
 rec['empty']=snapshot('empty-recipient-build',dest,recipient_target);assert not any(fresh for _,fresh in rec['empty']['compiler_messages'])
 for n in ('donor','donor-repeat','recipient','recipient-repeat','empty'):assert rec[n]['native_output']==rec[n]['source_order'],(case,n,rec[n])
 assert rec['recipient']['native_output']==rec['empty']['native_output']
 rec['donor_order_differs']=rec['donor']['native_output']!=rec['empty']['native_output'];rec['verdict']='fresh behavior';result[case]=rec;write('worktree-result.json',result)
 print(case,rec['worktree'],rec['donor_order_differs'],rec['recipient']['actual_script_execs'],rec['recipient']['elf_sha256']==rec['empty']['elf_sha256'],flush=True)
