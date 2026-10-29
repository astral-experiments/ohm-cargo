"""Compare actual legacy Cargo.lock metadata, checksum errors and rewrites with a local registry."""
import hashlib,json,os,shutil,subprocess as sp,sys,tempfile,tomllib
from pathlib import Path
def h(b):return hashlib.sha256(b).hexdigest()
def wr(f,b):
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_bytes(b.encode() if isinstance(b,str) else b)
def save(f,o):wr(f,json.dumps(o,sort_keys=True,indent=2)+"\n")
crates="registry+https://github.com/rust-lang/crates.io-index"
checksum="bd"*32
header="# lockfile compatibility experiment\n"
meta='[metadata]\n"example note" = "keep this string"\n'
def raw(style):
    root='[root]\n' if style.startswith("v1") else '[[package]]\n'
    deps=f'"bar 0.1.0 ({crates})"' if style.startswith("v1") else '"bar"'
    foo=root+'name = "foo"\nversion = "0.0.1"\n'+f'dependencies = [{deps}]\n\n'
    bar='[[package]]\nname = "bar"\nversion = "0.1.0"\n'+f'source = "{crates}"\n'
    v=''
    ex=meta
    if style in ("v3","v4","mixed","duplicate","future","bad-key","patch"):
        v='version = '+("3" if style=="v3" else "99" if style=="future" else "4")+'\n\n'
    if style.startswith("v1") or style=="mixed":
        tok=checksum
        if style=="v1-bad":tok="3b"*32
        if style=="v1-none":tok="<none>"
        ex+=f'"checksum bar 0.1.0 ({crates})" = "{tok}"\n'
    if not style.startswith("v1"):bar+=f'checksum = "{checksum}"\n'
    if style=="duplicate":foo+=bar+"\n"
    if style=="bad-key":ex+='"checksum bar 0.1.0 invalid-source" = "old"\n'
    extra='[[patch.unused]]\nname = "spare"\nversion = "0.1.0"\n\n' if style=="patch" else ""
    return (header+v+foo+bar+"\n"+extra+ex).encode()
def run(root,im,style,sdk):
    ws=root/"ws"; vendor=ws/"vendor/bar-0.1.0"
    wr(ws/".cargo/config.toml",'[source.crates-io]\nreplace-with = "vendored-sources"\n[source.vendored-sources]\ndirectory = "vendor"\n')
    mf='[package]\nname="foo"\nversion="0.0.1"\nedition="2021"\n[dependencies]\nbar="=0.1.0"\n'
    if style=="patch":
        mf+='[patch.crates-io]\nspare={ path="../spare" }\n'
        wr(root/"spare/Cargo.toml",'[package]\nname="spare"\nversion="0.1.0"\nedition="2021"\n')
        wr(root/"spare/src/lib.rs","pub fn answer()->u8{17}\n")
    wr(ws/"Cargo.toml",mf);wr(ws/"src/lib.rs","pub use bar::answer;\n")
    wr(vendor/"Cargo.toml",'[package]\nname="bar"\nversion="0.1.0"\nedition="2015"\n');wr(vendor/"src/lib.rs","pub fn answer()->u8{29}\n")
    save(vendor/".cargo-checksum.json",{"package":checksum,"files":{n:h((vendor/n).read_bytes()) for n in ("Cargo.toml","src/lib.rs")}})
    orig=raw(style);wr(ws/"Cargo.lock",orig)
    rv=root/"ru/toolchains/ohm";(rv/"bin").mkdir(parents=True)
    (rv/"bin/cargo").symlink_to(im);(rv/"bin/rustc").symlink_to(sdk/"bin/rustc");(rv/"lib").symlink_to(sdk/"lib",target_is_directory=True)
    env=dict(HOME=str(Path.home()),PATH=str(Path.home()/".cargo/bin")+":/usr/bin:/bin",RUSTUP_HOME=str(root/"ru"),RUSTUP_AUTO_INSTALL="0",
             CARGO_HOME=str(root/"cargo-home"),CARGO_TARGET_DIR=str(root/"target"),CARGO_BUILD_BUILD_DIR=str(root/"shared"),
             CARGO_NET_OFFLINE="true",CARGO_EXPERIMENTAL_RESOLVE_CACHE="1",CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never",CARGO_TERM_COLOR="never",LC_ALL="C")
    out=[]
    for i,args in enumerate([["metadata","--format-version","1","--locked","--offline"],["metadata","--format-version","1","--offline"],["metadata","--format-version","1","--locked","--offline"]]):
        if i==1:wr(ws/"Cargo.toml",mf+'\n[profile.fast-test]\ninherits="dev"\n')
        x=sp.run([str(Path.home()/".cargo/bin/cargo"),"+ohm",*args],cwd=ws,env=env,capture_output=True,timeout=8)
        raw_stdout=x.stdout.replace(os.fsencode(root),b"<fixture>")
        raw_err=x.stderr.replace(os.fsencode(root),b"<fixture>")
        wr(root/f"{i}.stderr",raw_err);wr(root/f"{i}.stdout",raw_stdout)
        encoded=(ws/"Cargo.lock").read_bytes();wr(root/f"{i}.lock",encoded)
        state={"exit":x.returncode,"stderr":h(raw_err),"stdout":h(raw_stdout),"lock":h(encoded)}
        if x.returncode==0:
            o=json.loads(raw_stdout); pkg_names=sorted(v["name"] for v in o["packages"]);assert pkg_names==["bar","foo"],(style,pkg_names)
            assert "keep this string" in encoded.decode()
        else:
            assert x.returncode==101 and raw_err,(style,i,x.returncode)
        out.append(state)
    return out
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("output","parent","candidate","sdk"):
        p.add_argument("--"+name,required=True,type=Path)
    a=p.parse_args()
    assert h((a.sdk/"bin/rustc").read_bytes())=="fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512", "different compatibility rustc"
    output=a.output.absolute()
    if os.path.lexists(output): raise ValueError("supply a new output directory")
    output.mkdir(mode=0o700)
    imgs=[a.parent.resolve(strict=True), a.candidate.resolve(strict=True)]
    shas=[h(i.read_bytes())for i in imgs];assert shas==["967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9","190829f32ebd9111c628ef50b26a350851aa92446184292732b18d0626635fdf"]
    results={}
    for style in ("v1","v1-bad","v1-none","v2","v3","v4","mixed","duplicate","future","bad-key","patch"):
        assert shutil.disk_usage(output).free>45*2**30+16*2**20
        arms=[run(output/a/style,im,style,a.sdk.resolve()) for a,im in zip("AB",imgs)]
        assert arms[0]==arms[1],(style,arms)
        if style in ("v1","v2","v3","v4","mixed","patch"):assert any(v["exit"]==0 for v in arms[0]),style
        if style in ("v1-bad","v1-none","duplicate","future","bad-key"):assert all(v["exit"]==101 for v in arms[0]),style
        results[style]=arms[0]
        print(style,[v["exit"]for v in arms[0]],flush=True)
    save(output/"complete.json",{"cases":results,"sha":shas,"commands":sum(len(v)*2 for v in results.values())})

