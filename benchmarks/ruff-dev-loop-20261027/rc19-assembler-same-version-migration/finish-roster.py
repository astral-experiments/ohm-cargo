"""Keep the stopped raw comparison and run the actual next no-op on its unchanged state."""
from pathlib import Path
import ast, hashlib, json, os, re, shutil, subprocess, sys

q=Path(__file__).resolve().parent
root=q/"coverage-v1";src=root/"work";sdk=root/"sdk";rh=root/"rustup"
assert hashlib.sha256((q/"roster.py").read_bytes()).hexdigest()=="54c4c954fe5031411fef9c2a38ac26192a5d56d7d11cfe277d31b1f48a196d24"
assert (q/"treatment-v1/broad-native-roster.exit").read_text().strip()=="1"
assert (q/"treatment-v1/broad-native-roster.stderr").read_text().strip().endswith("AssertionError")
module=ast.parse((q/"roster.py").read_text())
defs=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in ("sha","put","run")]
exec(compile(ast.Module(body=defs,type_ignores=[]),str(q/"roster.py"),"exec"))
env={"PATH":str(Path(shutil.which("rustup")).parent)+":/usr/bin:/bin","HOME":str(root/"home"),
     "CARGO_HOME":str(root/"cargo-home"),"RUSTUP_HOME":str(rh),"RUSTUP_AUTO_INSTALL":"0",
     "CARGO_INCREMENTAL":"0","CARGO_NET_OFFLINE":"true","LC_ALL":"C","LANG":"C"}
reports={p.parent.name:json.loads(p.read_bytes()) for p in root.glob("*/result.json")}
old=reports["parent-native-2"];new=reports["candidate-native-1"]
def keyed(rows):return {(n,tuple(k),t): (fresh,elf) for n,k,t,fresh,elf in rows}
a=keyed(old["units"]);b=keyed(new["units"])
assert set(a)==set(b) and len(a)==12
delta=[(k,a[k][1],b[k][1]) for k in sorted(a) if a[k][1] != b[k][1]]
assert len(delta)==1 and delta[0][0]==("only_bin_ex",("example",),True)
assert sorted(new["stock_links"])==sorted(n.removesuffix(".rlink-cache.json") for n in old["old_linkable"])
assert len(new["full"])==11 and not new["cached"]
run("candidate","native",2)
no=keyed(reports["candidate-native-2"]["units"])
assert set(no)==set(b) and all(no[k][0] and no[k][1]==b[k][1] for k in b)
put(root/"completion.json",{"initial_strict_status":1,"original_stderr":sha(q/"treatment-v1/broad-native-roster.stderr"),
                        "strict_mismatches":delta,"reports":{k:sha(root/k/"result.json") for k in reports},
                        "next_native_noop":True,"old":sha(q.parent/"ohm-propagated-link-paths-20261029/dirty-real-link-migrate-matched"),
                        "new":sha(sdk/"bin/cargo"),"full_version":sha(root/"old.version")})
