"""Read retained qualification files and immutable source archives. No compiler is executed."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib

def sha(body):
    return hashlib.sha256(body).hexdigest()

def git(repo, ref, path):
    return subprocess.check_output(["git", "-C", repo, "show", f"{ref}:{path}"])

def write(out, data):
    out.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")

def source_record(body, terms):
    lines = body.decode().splitlines()
    locations = {}
    for term in terms:
        indexes = [i for i, line in enumerate(lines, 1) if term in line]
        assert indexes, term
        locations[term] = indexes
    return {"sha256": sha(body), "literal_source_lines": locations}

def typed(rows, name):
    return [r for r in rows if r.get("reason") == "compiler-artifact" and r["target"]["name"] == name]

def collect_phase(path):
    native = json.loads((path / "native.json").read_bytes())
    rows = [json.loads(v) for v in (path / "cargo.jsonl").read_bytes().splitlines()]
    stderr = (path / "stderr").read_text()
    seen = []
    for e in native["events"]:
        if e["role"] != "rustc-full" or e["target"] != "ty_python_semantic":
            continue
        args = e["argv"]
        stem = next(t.split("=-", 1)[1] for t in args if t.startswith("extra-filename=-"))
        marker = f"ty_python_semantic-{stem}.d/ohm-foreign-span-bytes"
        assert marker in stderr
        externs = {t.split("=", 1)[0]: Path(t.split("=", 1)[1]).name for t in args if "=" in t and t.split("=", 1)[0] in ("salsa", "bitflags")}
        for n, artifact in externs.items():
            qualified = [r for r in typed(rows, n) if artifact in [Path(f).name for f in r["filenames"]]]
            assert len(qualified) == 1
            pkg = qualified[0]["package_id"]
            assert ("bitflags@2.11.0" in pkg) if n == "bitflags" else ("2f687a17ceea8ec7aaa605561ccbde938ccef086" in pkg)
        assert len(externs) == 2
        direct = sorted(set(Path(t.split("=", 1)[1]).name for i, t in enumerate(args) if i and args[i-1] == "--extern" and t.endswith(".so")))
        seen.append({"stem": stem, "test_harness": "--test" in args, "argv_sha256": e["argv_sha256"], "missing": marker, "direct_macro_so": direct, "typed_externs": externs})
    assert seen
    macro = typed(rows, "salsa_macros")
    assert len(macro) == 1
    cfg = [r["cfgs"] for r in rows if r.get("reason") == "build-script-executed" and "proc-macro2@1.0.106" in r["package_id"]]
    assert len(cfg) == 1 and {"wrap_proc_macro", "proc_macro_span"} <= set(cfg[0])
    return {"raw": {f: sha((path / f).read_bytes()) for f in ("native.json", "cargo.jsonl", "stderr", "status.json")}, "semantic": seen, "proc_macro2_cfg": cfg[0], "salsa_macro_artifact": [Path(f).name for f in macro[0]["filenames"]]}

p = argparse.ArgumentParser()
for key in ("held", "cargo", "rust", "ruff", "registry", "out"):
    p.add_argument("--" + key, required=True, type=Path)
a = p.parse_args()
rev = "2d6ce561250a464e1fa231ef30e54d0f029f76a4"
parent = "716260bf10d7ae1d965ed9b22653e57fbc960582"
rust = "a4fa11bcd38280639cb94daacc125472657db6c3"
cargo = "235f9228651b74c591e6f62cae4c9b761448dd2d"
salsa = "2f687a17ceea8ec7aaa605561ccbde938ccef086"
paths = {
    "synstructure": ("0.13.2", {"src/lib.rs": ["Span::call_site().located_at(field.span())", "binding: format_ident!"]}),
    "syn": ("2.0.117", {"src/spanned.rs": ["self.__span()"], "src/data.rs": ["impl ToTokens for Field {", "self.ty.to_tokens(tokens)"]}),
    "quote": ("1.0.45", {"src/spanned.rs": ["join_spans(self.into_token_stream())", "first.join(last)"]}),
    "proc-macro2": ("1.0.106", {"src/wrapper.rs": ["Span::Compiler(proc_macro_span::join(a, b)?)"], "src/probe/proc_macro_span.rs": ["this.join(other)"]}),
    "bitflags": ("2.11.0", {"src/public.rs": ["struct $PublicBitFlags(<$PublicBitFlags as $crate::__private::PublicFlags>::Internal)"]}),
}
lock = git(a.ruff, rev, "Cargo.lock")
assert lock == git(a.ruff, parent, "Cargo.lock")
packages = {(r["name"], r["version"]): r for r in tomllib.loads(lock.decode())["package"]}
cert = {"ruff": rev, "ruff_parent": parent, "rust": rust, "cargo": cargo, "salsa": salsa, "lock_sha256": sha(lock), "registry": {}, "sources": {}, "bitflags_updates": {}}
for name, (version, terms) in paths.items():
    filename = f"{name}-{version}.crate"
    file = a.held / filename if name == "bitflags" else a.registry / filename
    digest = packages[(name, version)]["checksum"]
    assert sha(file.read_bytes()) == digest
    cert["registry"][name] = {"version": version, "archive_sha256": digest}
    with tarfile.open(file) as ar:
        for path, needles in terms.items():
            key = f"{name}-{version}/{path}"
            cert["sources"][key] = source_record(ar.extractfile(key).read(), needles)
salsa_source = (a.held / "salsa-update.rs").read_bytes()
blob = hashlib.sha1(f"blob {len(salsa_source)}\0".encode() + salsa_source).hexdigest()
assert blob == "e3a78ee1a19d1cfc9dfc057f8f141375b64b61cd"
cert["sources"]["salsa/components/salsa-macros/src/update.rs"] = {**source_record(salsa_source, ["synstructure::Structure::new(&input)", "quote!(#tokens #binding,)"]), "git_blob": blob}
for proj, repo, commit, path, terms in [
    ("rust", a.rust, rust, "compiler/rustc_expand/src/proc_macro_server.rs", ["fn span_debug(", "fn span_join(", "fn span_subspan(", "fn span_source_text(", "fn span_byte_range(", "fn observe_foreign_span(", "krate: expn_data.macro_def_id", "self.observe_foreign_span()"]),
    ("rust", a.rust, rust, "compiler/rustc_interface/src/passes.rs", ["sess.proc_macro_observed_foreign_bytes.load", 'path.join("ohm-untrackable-foreign-span")', 'path.join("ohm-foreign-span-bytes")']),
    ("cargo", a.cargo, cargo, "src/compiler/fingerprint/dep_info.rs", ["Even an intact record marked complete must keep the missing input", "on_disk_info.observer = Some(on_disk_info.files.len())"]),
]:
    cert["sources"][f"{proj}/{path}"] = source_record(git(repo, commit, path), terms)

ruff_files = subprocess.check_output(["git", "-C", a.ruff, "ls-tree", "-r", "--name-only", rev, "--", "crates/ty_python_semantic/src"]).decode().splitlines()
macro_count = 0
for path in ruff_files:
    if not path.endswith(".rs"):
        continue
    body = git(a.ruff, rev, path).decode()
    for block in re.finditer(r"(?m)^\s*(?:bitflags::)?bitflags!\s*\{(.*?)\bstruct\s+(\w+)\s*:", body, re.S):
        macro_count += 1
        assert not re.search(r"\b(?:Serialize|Deserialize)\b", block.group(1))
        if "salsa::Update" in block.group(1):
            assert body.encode() == git(a.ruff, parent, path)
            cert["bitflags_updates"][block.group(2)] = {"path": path, "derive_line": body.count("\n", 0, body.index("salsa::Update", block.start(1), block.end(1))) + 1, "file_sha256": sha(body.encode())}
assert macro_count == 12 and len(cert["bitflags_updates"]) == 4
cert["all_bitflags_invocations"] = macro_count
observed = {}
for mode, folder in {"check": a.held/"raw", "build": a.held/"native-workflows"/"qualified-native-build", "test": a.held/"native-workflows"/"qualified-native-test"}.items():
    observed[mode] = {f"{direction}-unchanged-{n}": collect_phase(folder/f"{direction}-unchanged-{n}") for direction in ("parent", "child") for n in (1, 2)}
write(a.out/"source.json", cert)
write(a.out/"observed.json", observed)
