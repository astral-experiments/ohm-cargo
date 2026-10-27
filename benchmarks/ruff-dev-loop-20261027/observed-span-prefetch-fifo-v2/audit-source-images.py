"""Match every source byte mounted for a local Cargo PGO build back to the actual frozen Git tree."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
h=Path(__file__).resolve().parent;r=Path('/dev/shm/ohm-cargo-scout-sdk-pgo-build-20261027');repo=Path('/home/dev-user/code/oss/ohm-cargo-observer-sdk-prefetch-20261027');out=h.parent/'ruff-sdk-prefetch-corrected-subjects'
revs={'parent253':'d577be8eb1db7a3a4e4a82246d64644aaf3e0bff','guardv3':'d38fdd02503662de04c52f5f370f5dd81bddf868','stackv5':'f4c3de3aafcc75de51a0e510cc6cf36cf0366459'}
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
for arm in sys.argv[1:] or list(revs):
    src=r/('corrected-source-'+arm);rev=revs[arm];rows=git('ls-tree','-rz',rev).split(b'\0');rows=[q for q in rows if q];expected=set();summary={}
    for row in rows:
        meta,name=row.split(b'\t',1);mode,typ,oid=meta.split();p=src/os.fsdecode(name);expected.add(name);assert typ==b'blob',(mode,typ,name)
        data=os.fsencode(os.readlink(p)) if mode==b'120000' else p.read_bytes();actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest().encode();assert actual==oid,(arm,os.fsdecode(name),oid,actual)
        if mode!=b'120000':assert bool(p.stat().st_mode&0o111)==(mode==b'100755'),(arm,name,mode,p.stat().st_mode)
        if name in {b'Cargo.lock',b'src/compiler/fingerprint/mod.rs',b'src/compiler/fingerprint/dep_info.rs',b'src/compiler/mod.rs',b'src/ops/cargo_worktree/mod.rs'}:summary[os.fsdecode(name)]=hashlib.sha256(data).hexdigest()
    actual={os.fsencode(str(p.relative_to(src))) for p in src.rglob('*') if p.is_symlink() or p.is_file()};assert actual-expected=={b'git-commit-info'} and not expected-actual,(actual-expected,expected-actual)
    rc={'name':arm,'commit':rev,'tree':git('rev-parse',rev+'^{tree}').decode().strip(),'checked_git_blob_count':len(expected),'source_tarball_generated_metadata_sha256':digest(src/'git-commit-info'),'source_sha256':summary,'cargo_sha256':digest(out/arm),'version':subprocess.check_output([out/arm,'-Vv'],text=True).splitlines(),'compiler_and_profile_inputs':(h/(arm+'.inputs')).read_text().splitlines()[-3:],'pgo_data_sha256':'481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7','cargo_invocation':'cargo +ohm build --release --locked --offline -p cargo --bin cargo --features ohm-defaults -j6','rustflags':['-Cprofile-use=<same-external-training-profdata>','-Cllvm-args=-pgo-warn-missing-function=false'],'cpu_affinity':'0-3','native_release_channel':'dev','incremental':False,'scope':'Task-private host tmpfs mapped onto identical pinned canonical Cargo source, registry-home, target and shared paths for all arms. Same tarball commit metadata holds the display version and registry parser cache namespace constant.'};e=h/(arm+'.manifest.json');e.write_text(json.dumps(rc,indent=2)+'\n');print(arm,rev,rc['cargo_sha256'],rc['checked_git_blob_count'],flush=True)
