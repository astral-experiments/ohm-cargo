"""Read the rejected run, controls, exact input certificates and owned parent modes before any repair."""
import hashlib,json,os,stat,subprocess
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-paths-over261-20261028');old=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028');R=Path('/home/dev-user/code/oss/ruff-output-paths-over261-20261028');Q=H/'qualified-261-workspace/workspace/qual'
def h(f):return hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
def info(p):
 st=p.lstat();return dict(mode=oct(stat.S_IMODE(st.st_mode)),uid=st.st_uid,gid=st.st_gid,ino=st.st_ino,dev=st.st_dev)
idx=Path(subprocess.check_output(['git','-C',R,'rev-parse','--path-format=absolute','--git-path','index'],text=True).strip())
rows=json.loads((Q/'trace-parent/record.json').read_bytes());assert len(rows['products'])==922 and rows['units']==501 and len(rows['physical'])==2
visible={str(x):info(x) for x in sorted(set([*H.parents,H,H/'cargo-home',old,old/'cargo-home',R,idx]))}
proofs={};n=0
for home in (old/'cargo-home',H/'cargo-home'):
 for sub in ('.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2'):
  p=home/sub;files={str(x.relative_to(p)):h(x) for x in sorted(p.rglob('*')) if x.is_file()};proofs[str(p)]=dict(present=p.exists(),mode=info(p) if p.exists() else None,count=len(files),files_sha=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest())
  n+=bool(files)
assert n==2 and not any((H/'cargo-home'/k).exists() for k in ('.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2')) and visible[str(H)]['mode']=='0o775' and visible[str(old)]['mode']=='0o700';assert not (H/'scoring.grant').exists() and not list((H/'qualified-261-workspace').glob('*/ir/*/record.json'))
before=Q/'saved-dotd-parent';current=H/'workspace/target/debug';dot={str(f.relative_to(before)):h(f) for f in before.rglob('*') if f.is_file()};assert len(dot)==58 and all(h(current/k)==v for k,v in dot.items())
positive=json.loads((H/'port-migration-v2/complete.json').read_bytes());assert len(positive)==6
print(json.dumps(dict(host=os.uname().nodename,uname=os.uname().release,euid=os.geteuid(),ancestors=visible,proofs=proofs,initial_slots=0,original_h7='opened after c776e0cc7a0cbda6955c67ad4f306676871ab822',subject=h(H/'qualified-pair.json'),original_plan=h(H/'plan.json'),rejected_audit=h(Q/'trace-parent/record.json'),rejected_stdout=h(Q/'trace-parent/stdout'),native_migration=h(H/'port-migration-v2/complete.json'),prep=h(H/'ready.json'),source=h(R/'crates/ty_python_semantic/src/types/relation.rs'),index_path=str(idx),index_sha=h(idx),public_deps=dot,products={n:[h(Path(n)),info(Path(n))['dev'],info(Path(n))['ino'],Path(n).stat().st_size,Path(n).stat().st_mtime_ns] for n in rows['products']}),indent=2,sort_keys=True))
