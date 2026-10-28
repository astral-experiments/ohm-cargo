"""Distinguish a deliberately symlinked user manifest from generated Cargo markers."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
sdk=Path.home()/".cache/ohm-ron-producer-freshness-20261028/official-sdk"
cargo={"original":sdk/"bin/cargo","corrected":Path("/dev/shm/ohm-marker-corrected-20261028/cargo")}
assert [sha(c)for c in cargo.values()]==["02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573","a19d515cc301c05ad345ad0d657508905c28a2c900e01963632724cfd3b7289a"]
results=[]
for name,c in cargo.items():
    r=Path(tempfile.mkdtemp(prefix="ohm-user-manifest-",dir="/dev/shm"));src=r/"app"
    for d in ("app/src","localdep/src","owned-manifest","rustup/toolchains","registry","home","target","shared","tmp"):
        (r/d).mkdir(parents=True)
    (r/"rustup/toolchains/ohm").symlink_to(sdk)
    for d in (src,r/"localdep"):(d/"src/lib.rs").write_text("pub fn ok() {}\n")
    (r/"localdep/Cargo.toml").write_text('[package]\nname="localdep"\nversion="0.1.0"\nedition="2024"\n')
    contents='[package]\nname="app"\nversion="0.1.0"\nedition="2024"\n'; original=r/"owned-manifest/manifest.toml";original.write_text(contents)
    manifest=src/"Cargo.toml";manifest.symlink_to(original);inode=manifest.lstat().st_ino
    proxy=Path.home()/".cargo/bin/cargo"
    env={"PATH":str(proxy.parent)+":/usr/local/bin:/usr/bin:/bin","LANG":"C.UTF-8","HOME":str(r/"home"),"CARGO_HOME":str(r/"registry"),"RUSTUP_HOME":str(r/"rustup"),"RUSTUP_TOOLCHAIN":"ohm","TMPDIR":str(r/"tmp"),"CARGO_TARGET_DIR":str(r/"target"),"CARGO_BUILD_BUILD_DIR":str(r/"shared"),"CARGO_NET_OFFLINE":"true"}
    entry=["bwrap","--die-with-parent","--ro-bind","/","/","--dev","/dev","--proc","/proc","--bind",str(r),str(r)]
    if name=="corrected":entry+=["--ro-bind",str(c),str(sdk/"bin/cargo")]
    args=["+ohm","add","--offline","--path","../localdep"]
    p=subprocess.run([*entry,"--chdir",str(src),"--","taskset","-c","28,29",str(proxy),*args],env=env,capture_output=True)
    assert p.returncode==0,(name,p.stderr.decode())
    actual=original.read_text()
    assert manifest.is_symlink() and manifest.readlink()==original and inode==manifest.lstat().st_ino
    assert actual.startswith(contents) and 'localdep = { version = "0.1.0", path = "../localdep" }' in actual,(name,actual)
    results.append({"arm":name,"cargo":sha(c),"command":args,"rc":p.returncode,"final_manifest":actual,"same_link_inode":True,"symlink_retained":True,"stderr_sha256":hashlib.sha256(p.stderr).hexdigest()})
print(json.dumps(results,indent=2,sort_keys=True))
