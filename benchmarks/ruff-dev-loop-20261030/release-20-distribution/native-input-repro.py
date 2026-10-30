"""Reproduce the #263 native-link regression with an unwrapped Ohm Cargo on x86-64 Linux."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path, help="new directory for the fixture, products and logs")
parser.add_argument("--toolchain", default="ohm")
parser.add_argument("--expect", choices=["fixed", "stale", "report"], default="report")
parser.add_argument("--zmij", action="store_true", help="use Ruff's locked offline zmij 1.0.10")
args = parser.parse_args()
if sys.platform != "linux" or platform.machine() != "x86_64":
    parser.error("the ELF entry probe requires Linux x86-64")
root = args.directory.absolute()
root.mkdir(parents=True, exist_ok=False)
project = root / "project"
for directory in ("src", "tests"):
    (project / directory).mkdir(parents=True)
def put(path, value):
    (project / path).write_text(value)
cargo = ["cargo", "+" + args.toolchain]
env = os.environ | {"CARGO_NET_OFFLINE":"true", "CARGO_TERM_COLOR":"never"}
for key in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
    if env.get(key): parser.error(f"run the repro without {key}")
assembly = 'pub fn get(mut x: usize) -> usize { unsafe { core::arch::asm!("mov {0}, {0}", inout(reg) x, options(nomem, nostack)); } x }\n'
if args.zmij:
    dep = 'zmij = "=1.0.10"'
    body = 'zmij::Buffer::new().format(7.0_f64).parse::<f64>().unwrap() as usize'
else:
    (project / "barrier/src").mkdir(parents=True)
    put("barrier/Cargo.toml", '[package]\nname="barrier"\nversion="0.0.0"\nedition="2024"\n')
    put("barrier/src/lib.rs", assembly)
    dep = 'barrier = { path = "barrier" }'
    body = 'barrier::get(7)'
put("Cargo.toml", '[package]\nname="native_recheck"\nversion="0.0.0"\nedition="2024"\n[dependencies]\n' + dep + '\n[profile.dev.package."*"]\nopt-level=1\n')
put("src/lib.rs", 'pub fn value() -> usize { ' + body + ' }\n')
put("tests/integration.rs", '#[test] fn result() { assert_eq!(native_recheck::value(), 7); }\n')
put("build.rs", """fn main() {
    let out = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
    println!("cargo::rerun-if-changed=build.rs");
    println!("cargo::rustc-link-search=native={}", out.display());
    if std::path::Path::new("seed.ld").exists() {
        std::fs::copy("seed.ld", out.join("libgcc_s.so")).unwrap();
    }
}
""")
# The original GCC linker script and the installed toolchain are read-only.
system = Path(subprocess.check_output(["gcc", "-print-file-name=libgcc_s.so"], text=True).strip()).resolve(strict=True)
observer = root / "observer.o"
asm = '.text\n.type ohm_observe,@function\nohm_observe:\n mov $231,%eax\n mov $83,%edi\n syscall\n ud2\n.section .preinit_array,"aw",@preinit_array\n.quad ohm_observe\n.section .note.GNU-stack,"",@progbits\n'
subprocess.run(["as", "--64", "-o", observer], input=asm, text=True, check=True)
if any('"' in str(p) or '\n' in str(p) for p in (observer, system)): parser.error("unsupported GNU script path")
valid = f'INPUT ( "{observer}" "{system}" )\n'.encode()
invalid = b"OHM_REJECT_MALFORMED_NATIVE_SCRIPT\n"
seed = project / "seed.ld"
def select(p, data):
    if data is None: p.unlink(missing_ok=True)
    else: p.write_bytes(data)
def settings(group):
    return env | {"CARGO_TARGET_DIR":str(root / group / "target"), "CARGO_BUILD_BUILD_DIR":str(root / group / "build")}
subprocess.run([*cargo, "generate-lockfile", "--offline"], cwd=project, env=settings("warm"), check=True)
if args.zmij:
    assert "30e0d8dffbae3d840f64bda38e28391faef673a7b5a6017840f2a106c8145868" in (project / "Cargo.lock").read_text()
records = {}
def build(label, group):
    proc = subprocess.run([*cargo, "test", "--locked", "--offline", "--test", "integration", "--no-run", "--message-format=json"],
                          cwd=project, env=settings(group), capture_output=True)
    (root / (label + ".jsonl")).write_bytes(proc.stdout)
    (root / (label + ".stderr")).write_bytes(proc.stderr)
    rows = [json.loads(line) for line in proc.stdout.splitlines()]
    assert proc.returncode in (0,101) and rows[-1] == {"reason":"build-finished", "success":proc.returncode==0}, proc.stderr[-900:]
    row = {"cargo":proc.returncode}
    if proc.returncode:
        assert b"OHM_REJECT_MALFORMED_NATIVE_SCRIPT" in proc.stdout + proc.stderr
        exe = None
    else:
        exe, = [Path(r["executable"]) for r in rows if r["reason"]=="compiler-artifact" and r["target"]["name"]=="integration"]
        run = subprocess.run([exe, "--exact", "result"], cwd=project, capture_output=True)
        (root / (label + ".test")).write_bytes(run.stdout + run.stderr)
        row.update(program=run.returncode, elf=hashlib.sha256(exe.read_bytes()).hexdigest())
    out, = [Path(r["out_dir"]) for r in rows if r["reason"]=="build-script-executed" and "native_recheck" in r["package_id"]]
    records[label] = row
    return out / "libgcc_s.so", exe
shadow, _ = build("warm_original", "warm")
assert not shadow.exists() and records["warm_original"]["program"] == 0
select(shadow, valid)
_, exe = build("unchanged_valid", "warm")
exe.unlink()
_, exe = build("forced_valid", "warm")
select(shadow, invalid)
build("unchanged_invalid", "warm")
exe.unlink(missing_ok=True)
build("forced_invalid", "warm")
for name, data in [("valid", valid), ("invalid", invalid)]:
    select(seed, data)
    build("independent_" + name, "empty-" + name)
assert records["forced_valid"]["program"] == records["independent_valid"]["program"] == 83
assert records["forced_invalid"]["cargo"] == records["independent_invalid"]["cargo"] == 101
verdict = (records["unchanged_valid"]["program"], records["unchanged_invalid"]["cargo"])
classification = {(83,101):"fixed", (0,0):"stale"}.get(verdict,"unexpected")
report = {"classification":classification, "records":records, "cargo":subprocess.check_output([*cargo, "-Vv"], cwd=project,env=settings("warm"),text=True), "rustc":subprocess.check_output(["rustc","+" + args.toolchain,"-vV"],cwd=project,env=settings("warm"),text=True)}
(root / "result.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({"classification":classification, "unchanged":verdict, "forced":[83,101], "independent":[83,101], "report":str(root / "result.json")},indent=2))
if classification=="unexpected" or (args.expect!="report" and classification!=args.expect):sys.exit(1)
