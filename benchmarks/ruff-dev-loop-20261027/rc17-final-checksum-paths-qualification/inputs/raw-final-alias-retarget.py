"""Exercise a real symlink target change after a healthy initial checksum capture."""
from pathlib import Path
import json,hashlib,shutil,os,subprocess,sys
T=Path('/mnt/devbox-scratch/dev-user/ohm-observer-shipping-20261027');out=Path(sys.argv[1]);out.mkdir();frozen=T/'assets'
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,j):p.write_text(json.dumps(j,indent=2)+'\n')
summ={}
for name,sdk,cargo in [('published',frozen/'stock16-sdk',frozen/'stock16-sdk/bin/cargo'),('fixed',Path(os.environ['QUALIFIED_SDK']),Path(os.environ['QUALIFIED_CARGO']))]:
 b=out/name;b.mkdir();rustup=b/'rustup';(rustup/'toolchains').mkdir(parents=True);(rustup/'toolchains/ohm').symlink_to(sdk)
 for flags in [[],['-Zohm-worktree-seeds=no','-Zchecksum-freshness']]:
  for edit in ['retarget','replace-file']:
   state=b/(('default' if not flags else 'seed-off')+'-'+edit);src=state/'source';(src/'src').mkdir(parents=True);(src/'Cargo.toml').write_text('[package]\nname="alias_reader"\nversion="0.1.0"\nedition="2024"\n[workspace]\n')
   (src/'src/main.rs').write_text('fn main(){println!("{}",include_bytes!("../alias space/value.bin")[0]);}\n')
   for n,val in [('one',17),('two',29),('alias\\ space',17)]:
    (src/n).mkdir();(src/n/'value.bin').write_bytes(bytes([val,255,0,254]))
   alias=src/'alias space';alias.symlink_to('one',target_is_directory=True)
   rows=[]
   def run(label,cold=False):
    tmp=state/label;tmp.mkdir();wd=state/('cold' if cold else 'warm');(wd/'target').mkdir(parents=True,exist_ok=True);(wd/'shared').mkdir(exist_ok=True)
    env=dict(os.environ,PATH='/home/dev-user/.cargo/bin:/usr/bin:/bin',RUSTUP_HOME=str(rustup),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(state/'cargo-home'),CARGO_BUILD_BUILD_DIR=str(wd/'shared'),CARGO_TARGET_DIR=str(wd/'target'));env.pop('RUSTUP_TOOLCHAIN',None)
    # Physical source inputs remain unchanged. Only the executable bind varies by designated arm.
    cmd=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(state),str(state),'--ro-bind',str(cargo),str(sdk/'bin/cargo'),'--chdir',str(src),'--','cargo','+ohm',*flags,'build','--offline','--message-format=json']
    r=subprocess.run(cmd,env=env,capture_output=True,timeout=60);(tmp/'cargo.jsonl').write_bytes(r.stdout);(tmp/'stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr[-1000:];unit,=[q for z in r.stdout.splitlines() if (q:=json.loads(z)).get('reason')=='compiler-artifact']
    output=subprocess.check_output([unit['executable']]);(tmp/'stdout').write_bytes(output);fp,=[f for f in wd.rglob('dep-bin-alias_reader') if b'value.bin' in f.read_bytes()]; dd,=[f for f in wd.rglob('*.d') if b'# checksum:' in f.read_bytes() and b'value.bin' in f.read_bytes()];shutil.copyfile(dd,tmp/'rustc.d');shutil.copyfile(fp,tmp/'fingerprint')
    rows.append(dict(phase=label,fresh=unit['fresh'],runtime=int(output),wire=fp.read_bytes()[5],root=str(src),actual=os.readlink(alias),cargo=h(cargo),exe=h(Path(unit['executable']))))
   run('first');run('noop')
   if edit=='retarget':old=src/'swap';old.symlink_to('two',target_is_directory=True);os.replace(old,alias)
   else:
    original=src/'one/value.bin';stamp=original.stat();original.write_bytes((src/'two/value.bin').read_bytes());os.utime(original,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
   run('change');run('clean',True);save(state/'results.json',rows);summ[str(state.relative_to(out))]=[(x['fresh'],x['runtime'],x['wire']) for x in rows];save(out/'result.json',summ)
for name,rows in summ.items():
 assert rows[0][:2]==(False,17) and rows[1][:2]==(True,17) and rows[3][:2]==(False,29),(name,rows)
 expected=(True,17) if name=='published/seed-off-retarget' else (False,29)
 assert rows[2][:2]==expected,(name,rows,expected)
print(json.dumps(summ))
