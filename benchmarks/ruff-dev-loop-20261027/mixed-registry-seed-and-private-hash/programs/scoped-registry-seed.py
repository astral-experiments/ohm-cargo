"""Materialize a genuine registry-only Cargo run and inspect its full-workspace identity."""
from pathlib import Path
import fcntl, json, os, shutil, subprocess, sys

x = Path.home() / ".cache/ohm-233-position-qualified-20261027"
w = x / "mixed-native-abc-protocol-h3-v2"
historical = x / "mixed-native-full-abc-h3-v2"
out = x / "mixed-registry-input-qualification-v1"
sys.path.insert(0, str(w))
from common import CARGO_HOME, FROZEN, P, RUFF, SHARED, TARGET, dump, env, load, need, sha
from namespace import skeleton, spawn_args
from processes import records
from state import gate_free, seed, source_binds, source_clean

def argv_of(path, name):
    return [a for _, f, a in records(path) if Path(f).name == "rustc" and "--crate-name" in a and a[a.index("--crate-name") + 1] == name]

def signature(args):
    return [x for x in args if not x.startswith("--diagnostic-width=")]

def artifact_rows(path):
    return [v for line in (path / "stdout").read_bytes().splitlines() if (v := json.loads(line)).get("reason") == "compiler-artifact"]

def physical(state, path):
    p = Path(path)
    for root, key in [(TARGET, "target"), (SHARED, "shared")]:
        if p.is_relative_to(root):
            return state / key / p.relative_to(root)
    raise ValueError(p)

with (P / "native-measure.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    need(not out.exists(), "dedicated new location")
    gate_free(x, 85 * 2**30)
    out.mkdir(mode=0o700)
    source_index = source_clean()
    source_binding = load(w / "runner-binding.json")
    arm = source_binding["arms"]["B"]
    need(sha(Path(arm["cargo"])) == arm["cargo_sha256"] and sha(Path(arm["driver"])) == arm["driver_sha256"], "immutable subject")
    fixture = historical / "fixture"
    mount = skeleton(out)
    dump(out / "mount.json", mount)
    state = seed(out / "scoped-B", fixture, CARGO_HOME)
    params = spawn_args(mount, out, state, state / "registry-home", [], Path(arm["cargo"]), Path(arm["driver"]))
    ix = params.index("--")
    params[ix:ix] = source_binds(state)
    scoped = out / "scoped-registry"
    scoped.mkdir()
    cmd = ["cargo", "+ohm", "build", "--locked", "--offline", "-p", "get-size-derive2@0.11.0", "--message-format=json"]
    with (scoped / "stdout").open("xb") as so, (scoped / "stderr").open("xb") as se:
        z = subprocess.run([*params, "strace", "-ff", "-qq", "-s", "1048576", "-e", "trace=execve,execveat,prctl",
                            "-o", str(scoped / "exec"), *cmd], env=env(), cwd=RUFF, stdout=so, stderr=se)
    dump(scoped / "invocation.json", {"cargo": arm, "command": cmd, "status": z.returncode, "source_index": source_index})
    need(z.returncode == 0, (scoped / "stderr").read_text()[-2500:])
    rows = artifact_rows(scoped)
    need(rows and all(v["package_id"].startswith("registry+") for v in rows), "workspace artifact in scoped donor")
    full = historical / "receipts/build/B/cold"
    fr = next(row for row in artifact_rows(full) if row["target"]["name"] == "get_size_derive2")
    sr = next(row for row in rows if row["target"]["name"] == "get_size_derive2")
    full_argv, own_argv = (argv_of(q, "get_size_derive2") for q in (full, scoped))
    need(len(full_argv) == len(own_argv) == 1, "ambiguous compiler")
    mapped = {"fixed_full": full_argv[0], "scoped": own_argv[0]}
    def root_of(v):
        return [a for a in v if a.startswith(("-Cmetadata=", "metadata=", "-Cextra-filename=", "extra-filename=", "feature=", "--cfg"))]
    report = {"command": cmd, "package_ids": [v["package_id"] for v in rows], "scoped_product": sr,
              "full_product": fr, "root_controls": {k: root_of(v) for k, v in mapped.items()}, "argv": mapped,
              "scoped_binary_sha256": sha(physical(state, sr["filenames"][0])),
              "full_binary_sha256": sha(physical(historical / "state/build/B", fr["filenames"][0])),
              "exact_workspace_argv": signature(full_argv[0]) == signature(own_argv[0]),
              "physical_output_paths_match": fr["filenames"] == sr["filenames"],
              "source_index": source_index, "free_after": gate_free(out, 82 * 2**30), "native_comparison_samples": 0}
    dump(out / "scoped.json", report)
    need(source_clean() == source_index, "Ruff source identity")
    print("registry packages", len(rows), "same full workspace argv", report["exact_workspace_argv"],
          "same paths", report["physical_output_paths_match"], "full", fr["filenames"], "scoped", sr["filenames"], flush=True)
