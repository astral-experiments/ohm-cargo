"""Verify the exact legacy and versioned native marker regression using stock 1.99 Rust."""
import gzip
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

P = "2554a1dfaf22474b360a4298883acf41f82bd78f"
C = "8269d772aa1ef02e5efaa331dfb40eb55d71f719"
TREES = {P: "014d4b308410fdaa2acdadaff6aba2a410fc43da", C: "2391718877e88c16c6bc2b99ec9c6831f10b5288"}
DEP = "src/compiler/fingerprint/dep_info.rs"
FP = "src/compiler/fingerprint/mod.rs"
TEST = "tests/testsuite/freshness.rs"
BOUND = b"#[cfg(test)]\nmod encoded_dep_info {"
UNIT = "compiler::fingerprint::dep_info::encoded_dep_info::recheck_links_only_for_the_compiler_generated_marker"
OLD = "freshness::legacy_native_recheck_reuses_codegen_until_the_root_changes"
V2 = "freshness::native_recheck_reuses_codegen_until_the_root_changes"
REF = "refs/heads/charlie/qa-rc22-both-markers-20261031"

def call(*args, **kw):
    return subprocess.check_output(args, **kw)

def git(*args):
    return call("git", *args).decode().strip()

def file_at(rev, name):
    return call("git", "show", rev + ":" + name)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def projected(rev):
    assert git("rev-parse", C + "^") == P
    assert git("diff", "--name-only", P, C).splitlines() == [DEP, FP, TEST]
    assert git("rev-parse", rev + "^{tree}") == TREES[rev]
    old, new = file_at(P, DEP), file_at(C, DEP)
    assert old.count(BOUND) == new.count(BOUND) == 1
    op, ot = old.split(BOUND); cp, ct = new.split(BOUND)
    assert op != cp and ot != ct and b"inputs.pop();" in op and b"inputs.pop();" not in cp
    base_fp = file_at(P, FP); fixed_fp = file_at(C, FP)
    assert b'"ohm-declared-native-inputs-v1"' in base_fp and b'"ohm-declared-native-inputs-with-versioned-rechecks-v1"' in base_fp
    assert b'"ohm-checked-native-inputs-v3"' in fixed_fp and b'"ohm-declared-native-inputs-v1"' not in fixed_fp
    return {DEP: (op if rev == P else cp) + BOUND + ct, TEST: file_at(C, TEST), FP: file_at(rev, FP)}

def main():
    role = sys.argv[1]; rev = {"parent":P, "fixed":C}[role]
    projected_files = projected(rev)
    if "--inspect-only" in sys.argv:
        print(json.dumps({k:digest(v) for k,v in projected_files.items()},sort_keys=True));return
    assert os.environ["GITHUB_REF"] == REF
    qa = os.environ["GITHUB_SHA"]
    assert git("rev-parse","HEAD") == qa and git("rev-parse",qa+"^") == C
    assert set(git("diff","--name-only",C,qa).splitlines()) == {".github/workflows/ci.yml","ci/rc22-marker-qa.py"}
    out=Path(os.environ["RUNNER_TEMP"])/"marker-receipts"
    out.mkdir(exist_ok=False)
    def save(n, data):
        (out/n).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    call("git","checkout","--detach",rev)
    assert git("status","--porcelain") == ""
    for name, data in projected_files.items():
        path=Path(name)
        assert path.read_bytes()==file_at(rev,name)
        if path.read_bytes()!=data:
            path.write_bytes(data)
    physical = {p:file_digest(p) for p in (DEP,FP,TEST)}
    assert physical=={p:digest(b) for p,b in projected_files.items()}
    diff=git("diff","--name-only").splitlines()
    assert diff==([DEP,TEST] if rev==P else [])
    assert Path(DEP).read_bytes().split(BOUND)[0]==file_at(rev,DEP).split(BOUND)[0]
    assert git("ls-files","--others","--exclude-standard")==""
    lines = Path(DEP).read_text().splitlines(); unitline, = [i for i,l in enumerate(lines,1) if 'assert_eq!(parsed.recheck_dependent_links, synthetic);' in l]
    integline, = [i for i,l in enumerate(Path(TEST).read_text().splitlines(),1) if l.strip()=='assert_eq!(build(), "link:app\\n");']
    tools = {}
    for name in ("rustc","cargo"):
        path=Path(call("rustup","which","--toolchain","1.99.0",name).decode().strip())
        vv=call(str(path),"-vV").decode()
        assert re.search(r"^release: 1\.99\.0$",vv,re.M) or name=="cargo" and "cargo 1.99.0" in vv
        tools[name]={"path":str(path),"sha256":file_digest(path),"vv":vv}
    assert "b940084d7eb6a299eb4bfeb8e34901bc051e7ac4" in tools["rustc"]["vv"]
    source={"role":role,"role_sha":rev,"tree":TREES[rev],"qa":qa,"head_tree":git("rev-parse","HEAD^{tree}"),"host":platform.platform(),"github_run":os.environ["GITHUB_RUN_ID"],"physical":physical,"source_diff_paths":diff,"active_production_prefix":digest(Path(DEP).read_bytes().split(BOUND)[0]),"unit_test_module":digest(Path(DEP).read_bytes().split(BOUND)[1]),"stock":tools,"panic_lines":{"unit":unitline,"legacy":integline},"storage":os.environ["QA_STORAGE"]}
    save("source.json",source)
    cmd=["cargo","+1.99.0","test","--locked","-p","cargo","--lib","--test","testsuite","--no-run","--message-format=json"]
    print("Source",rev,TREES[rev],"compiling",flush=True)
    p=subprocess.run(cmd,capture_output=True)
    for k,data in (("stdout",p.stdout),("stderr",p.stderr)):
        (out/("build."+k+".gz")).write_bytes(gzip.compress(data,mtime=0))
    if p.returncode:
        print(p.stderr.decode(errors="replace")[-3500:]);print(p.stdout.decode(errors="replace")[-3500:]);sys.exit(p.returncode)
    builds=[json.loads(l) for l in p.stdout.splitlines() if l.startswith(b"{")]
    assert builds[-1]=={"reason":"build-finished","success":True}
    exes={}
    for msg in builds:
        target=msg.get("target",{})
        if msg.get("reason")=="compiler-artifact" and msg["profile"]["test"] and (target.get("name"),target.get("kind")) in [("cargo",["lib"]),("testsuite",["test"])]:
            assert target["name"] not in exes and msg["executable"];exes[target["name"]]=msg["executable"]
    assert set(exes)=={"cargo","testsuite"}
    cargo=Path(os.environ["CARGO_TARGET_DIR"])/"debug/cargo"
    real_env=os.environ.copy()
    real_env["PATH"]=str(Path(tools["rustc"]["path"]).parent)+os.pathsep+real_env["PATH"]
    real_env["RUSTUP_TOOLCHAIN"]="1.99.0"
    versions=call(str(cargo),"-Vv",env=real_env).decode()
    save("binaries.json",{"cargo":{"path":str(cargo),"sha256":file_digest(cargo),"vv":versions},"tests":{n:[s,file_digest(s)] for n,s in exes.items()},"build":cmd})
    puts={}
    for kind,name,exe in [("unit",UNIT,exes["cargo"]),("legacy",OLD,exes["testsuite"]),("v2",V2,exes["testsuite"])]:
        listed=call(exe,name,"--exact","--list",env=real_env).decode()
        assert re.search(r"^"+re.escape(name)+r": test$",listed,re.M) and "1 test, 0 benchmarks" in listed,listed
        (out/(kind+"-inventory.txt")).write_text(listed)
        args=[exe,name,"--exact","--include-ignored","--test-threads=1","--color","never"]
        q=subprocess.run(args,capture_output=True,env=real_env)
        for k,b in (("stdout",q.stdout),("stderr",q.stderr)): (out/(kind+"."+k)).write_bytes(b)
        raw=(q.stdout+q.stderr).decode(errors="replace");print(kind,raw[-2000:],flush=True)
        expect_fail=rev==P and kind in ("unit","legacy")
        signal=("FAILED" if expect_fail else "ok")
        gate=bool(re.search(r"^test "+re.escape(name)+r" \.\.\. "+signal+r"$",raw,re.M)) and "running 1 test" in raw and q.returncode==(101 if expect_fail else 0)
        gate=gate and re.search(r"test result: (?:FAILED|ok)\. "+("0 passed; 1 failed" if expect_fail else "1 passed; 0 failed")+r"; 0 ignored;",raw) is not None
        if expect_fail:
            loc=(DEP+":"+str(unitline) if kind=="unit" else TEST+":"+str(integline))
            assertion=("left: false" in raw and "right: true" in raw) if kind=="unit" else ('left: ""' in raw and 'right: "link:app\\n"' in raw)
            gate=gate and loc+":" in raw and assertion
        puts[kind]={"exact":name,"code":q.returncode,"expected_failure":expect_fail,"passed_gate":bool(gate),"args":args,"stdout":digest(q.stdout),"stderr":digest(q.stderr)}
        save("cases.json",puts)
    assert all(x["passed_gate"] for x in puts.values()),puts
    save("complete.json",{"run":os.environ["GITHUB_RUN_ID"],"qa":qa,"role":role,"source":rev,"cases":puts,"raw_file_sha256":{p.name:file_digest(p) for p in sorted(out.iterdir()) if p.is_file()}})
if __name__=="__main__":main()
