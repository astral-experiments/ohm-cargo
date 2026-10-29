from pathlib import Path
import hashlib,json,os,sys,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent))
import witness as w
root=w.base
w.base=root/"trait"
w.base.mkdir();(w.base/"receipts").mkdir()
w.live=w.base/"live";w.source=w.live/"src";w.seed=w.base/"seed"
w.source.mkdir(parents=True);(w.live/"tmp").mkdir()
for k,p in {"CARGO_HOME":"registry","CARGO_TARGET_DIR":"target","CARGO_BUILD_BUILD_DIR":"shared","TMPDIR":"tmp"}.items():w.env[k]=str(w.live/p)
w.put("Cargo.toml",'[workspace]\nresolver="3"\nmembers=["provider","reader","client"]\n')
w.put("provider/Cargo.toml",'[package]\nname="provider"\nversion="0.1.0"\nedition="2024"\n')
w.put("provider/build.rs",'fn main() { println!("cargo::rerun-if-changed=flag"); }\n')
w.put("provider/flag","stable\n")
w.put("reader/Cargo.toml",'[package]\nname="reader"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nprovider={path="../provider"}\n')
w.put("reader/src/lib.rs","pub use provider::{Supports, Token};\n")
w.put("client/Cargo.toml",'[package]\nname="client"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nreader={path="../reader"}\n')
w.put("client/src/lib.rs","fn accepts<T: reader::Supports>() {}\npub fn real_caller() { accepts::<reader::Token>(); }\n")
types="pub struct Token;\npub trait Supports {}\n"
impl="impl Supports for Token {}\n"
w.put("provider/src/lib.rs",types+impl)
subprocess.run([str(w.proxy),"+ohm","generate-lockfile","--offline"],cwd=w.source,env=w.env,check=True)
def oracle(label):
    saved={}
    for n in ["target","shared"]:
        p=w.live/n
        if p.exists():
            dst=w.base/(label+"-held-"+n);p.rename(dst);saved[n]=dst
    rec=w.run(label,trace=True)
    for n in ["target","shared"]:
        p=w.live/n
        if p.exists():p.rename(w.base/(label+"-computed-"+n))
        if n in saved:saved[n].rename(p)
    return rec
result={}
for label,data,expected in [("original",types+impl,0),("remove-impl",types,101),("restore-impl",types+impl,0)]:
    w.put("provider/src/lib.rs",data)
    warm=w.run(label,trace=True);cold=oracle(label+"-empty")
    assert warm["status"]==cold["status"]==expected
    assert warm["diagnostics"]==cold["diagnostics"],(warm,cold)
    if expected:assert any(r[1]["code"]=="E0277" for r in warm["diagnostics"]),warm["diagnostics"]
    assert warm["source_digests"]["reader/src/lib.rs"]==cold["source_digests"]["reader/src/lib.rs"]
    result[label]={"warm":warm["status"],"empty":cold["status"],"diagnostics":warm["diagnostics"],"reader_source":warm["source_digests"]["reader/src/lib.rs"],"client_source":w.sha(w.source/"client/src/lib.rs")}
last=w.run("restored-immediate",trace=True)
assert last["status"]==0 and all(f for _,f in last["compiler_artifacts"])
w.write(w.base/"terminal.json",result)
