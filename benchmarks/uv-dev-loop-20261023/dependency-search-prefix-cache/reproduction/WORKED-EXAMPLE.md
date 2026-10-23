# Portable rebuild and one-sample recipe

These commands use the existing fixture, atomic installer, and timed-command components included here. They do not require the historical private seal chain. They are a recipe for a **new, separately admitted study**, not an automatic qualification runner. Keep every attempted sample and stop on a failed prerequisite. Use only new task-owned directories and existing pinned tools.

## Build the two source variants

Set these paths to the package, an existing Ohm Cargo repository containing the embedded commit, an unused build root, and an existing stock 1.99.0 toolchain. All environment changes below are confined to the subshell.

```sh
(
  set -eu
  EVIDENCE_PACKAGE=/absolute/path/to/this/package
  EVIDENCE_REPO=/absolute/path/to/ohm-cargo
  EVIDENCE_BUILD=/absolute/path/to/new-build-root
  EVIDENCE_STOCK=/absolute/path/to/existing/1.99.0-x86_64-unknown-linux-gnu
  umask 077
  mkdir "$EVIDENCE_BUILD"
  mkdir "$EVIDENCE_BUILD/bin" "$EVIDENCE_BUILD/cargo-home" "$EVIDENCE_BUILD/tmp"
  git -C "$EVIDENCE_REPO" worktree add --detach "$EVIDENCE_BUILD/source" \
    5e5d271d763d7beb38b48755e22bd59e93f02b97
  git -C "$EVIDENCE_BUILD/source" apply \
    "$EVIDENCE_PACKAGE/source/baseline-from-embedded-head.patch"
  export CARGO_HOME="$EVIDENCE_BUILD/cargo-home"
  export CARGO_TARGET_DIR="$EVIDENCE_BUILD/target"
  export RUSTC="$EVIDENCE_STOCK/bin/rustc"
  export RUSTDOC="$EVIDENCE_STOCK/bin/rustdoc"
  export PATH="$EVIDENCE_STOCK/bin:/usr/bin:/bin"
  export TMPDIR="$EVIDENCE_BUILD/tmp" CARGO_TERM_COLOR=never
  export SSL_CERT_DIR=/usr/lib/ssl/certs SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER
  export CARGO_BUILD_JOBS=8 CARGO_INCREMENTAL=0
  export CARGO_PROFILE_RELEASE_OPT_LEVEL=3 CARGO_PROFILE_RELEASE_LTO=thin
  export CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 CARGO_PROFILE_RELEASE_DEBUG=1
  export CARGO_PROFILE_RELEASE_INCREMENTAL=false CARGO_PROFILE_RELEASE_STRIP=none
  export CFG_RELEASE_CHANNEL=dev LIBZ_SYS_STATIC=1
  cd "$EVIDENCE_BUILD/source"
  taskset -c 0-31 "$EVIDENCE_STOCK/bin/cargo" build --release --locked \
    --bin cargo --features all-static,ohm-defaults -j 8 -v
  cp "$EVIDENCE_BUILD/target/release/cargo" "$EVIDENCE_BUILD/bin/baseline.full"
  objcopy --strip-debug "$EVIDENCE_BUILD/bin/baseline.full" "$EVIDENCE_BUILD/bin/baseline"
  git apply "$EVIDENCE_PACKAGE/source/candidate.diff"
  taskset -c 8-23 "$EVIDENCE_STOCK/bin/cargo" build --release --locked \
    --bin cargo --features all-static,ohm-defaults -j 8 -v
  cp "$EVIDENCE_BUILD/target/release/cargo" "$EVIDENCE_BUILD/bin/candidate.full"
  objcopy --strip-debug "$EVIDENCE_BUILD/bin/candidate.full" "$EVIDENCE_BUILD/bin/candidate"
  sha256sum "$EVIDENCE_BUILD/bin/"*
)
```

Populate dependencies before freezing any cohort, either from a verified archive-only seed or a legitimate preparation build. Verify the source trees, complete compiler commands, nineteen static inputs, profile settings, and allocated-section preservation. The recipe builds both variants for portability; the original study instead reused its already accepted baseline. Different physical paths/tool inputs can produce different binary hashes. Record the fresh pair's hashes before any scored observation; do not substitute those hashes into the original result records.

## Prepare one fixed runtime context

Create an owned uv worktree at `3d82a6ad5a7eab8c68236553b7846517767c4b61`, a private Cargo home, and sibling `target`, `unused`, and `shared` paths under a new case root. `unused` must stay absent: it satisfies the old fixture's disjoint/equal-length target-name interface, while both measured variants use `target` and the fixture's `baseline` selector. Use a separate directory for copied binary inputs and one regular active Cargo file at `bin/cargo`.

In a task-scoped shell, configure `CARGO_HOME`, `CARGO_TARGET_DIR=CASE/target`, `CARGO_BUILD_BUILD_DIR=CASE/shared`, `CARGO_BUILD_JOBS=8`, and explicit `RUSTC`/`RUSTDOC` paths into the pinned Ohm 1.99.0-6 runtime. Keep the same fixed environment for both variants. Do not carry the producer's release/incremental overrides into this runtime shell. The accepted runtime had no explicit `RUSTFLAGS`, `CARGO_ENCODED_RUSTFLAGS`, or `CARGO_INCREMENTAL` override. Native ownership and shared-cache eligibility must pass unchanged; do not change ownership or policy to obtain sharing.

Populate dependency sources and warm the original `cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8` command before freezing the new cohort. Record the fresh source/tool/Cargo/namespace/rustc-info and output identities. The absolute workspace paths, directory hashes, inode/mtime values, binary hashes after rebuilding, and executable hashes are fixture-specific. The published uvx two-hash exception is not a portable allowlist. A different fixture must establish its own exact output equality or independently reviewed narrow exception **before effects are inspected**; unknown output differences fail.

## Execute one arm with the existing components

After staging/freezing the context, perform one fixed **30-second settle at stage entry**, before the first host observation or preflight. Do this once per stage, never per sample. Launch every Python controller on CPU8; the workload remains on CPUs0–7. For example, run `taskset -c 8 python3 -c 'import time; time.sleep(30)'` once, then run the saved block below with `taskset -c 8 python3 /path/to/owned-example.py` for each predeclared arm.

The following Python block is a concrete invocation recipe. Set `package`, `case`, `binary`, `cohort`, `sample`, `pair`, and `mode` to the newly frozen setup. `binary` selects one of the fixed variant inputs; `cohort` stays identical for both arms and all pairs of that stage. `sample` is a new directory per arm. Use `mode="preflight"` for excluded compiler-argv traces, `"ir"` for parent profiles, or `"native"` for uninstrumented wall samples. Set `native_stage=True` for both the native stage's preflights and timed arms; instruction stages use `False`. The actual workload command and verbosity stay unchanged.

```python
from pathlib import Path
import importlib.util, json, os, shutil

package = Path("/absolute/path/to/this/package")
case = Path("/absolute/path/to/new-case")
binary = Path("/absolute/path/to/frozen/baseline")  # candidate for the B arm
cohort = case / "new-stage"                       # one fixed batch per stage
sample = cohort / "pair-0-0-baseline"             # must not exist
pair, mode, native_stage = 0, "preflight", False
tools = Path("/absolute/path/to/pinned-profiling-tools")
strace = "/absolute/path/to/pinned-strace"

def component(name):
    spec = importlib.util.spec_from_file_location(name, package / "reproduction" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

fixture, portable, quiet, observer = map(component,
    ["dirty_fixture", "portable_components", "occupancy", "occupancy_observation"])
assert mode in ["preflight", "ir", "native"]
assert mode != "ir" or not native_stage
assert mode != "native" or native_stage
assert os.sched_getaffinity(0) == {8}
os.umask(0o077)
sample.mkdir(parents=True, exist_ok=False)
active, source = case / "bin/cargo", case / "uv/crates/uv/src/lib.rs"
backup, state = sample / "original-cargo", sample / "fixture"
original_stat = active.stat()
shutil.copy2(active, backup)
environment = dict(os.environ)
assert environment["CARGO_TARGET_DIR"] == str(case / "target")
assert environment["CARGO_BUILD_BUILD_DIR"] == str(case / "shared")
assert not any(k in environment for k in ["LD_PRELOAD", "LD_LIBRARY_PATH", "CARGO_LOG", "RUSTC_LOG"])
command = ["/usr/bin/taskset", "-c", "0-7", str(active), "-Zohm-defaults=yes",
           "test", "--no-run", "--locked", "--offline", "-j", "8"]
initialized = False
try:
    portable.install_variant(binary, active)
    active.chmod(original_stat.st_mode & 0o777)
    fixture.initialize(state, source, case / "uv",
                       {"baseline": case / "target", "candidate": case / "unused"}, case / "shared")
    initialized = True
    observation = quiet.require_quiet() if native_stage else observer.sample()
    (sample / "host-before-prepare.json").write_text(json.dumps(observation, indent=2) + "\n")
    fixture.prepare(state, cohort, "warmup" if mode == "preflight" else "measurement",
                    pair, "baseline", command, environment=environment)
    argv, child_environment = command, environment
    if mode == "preflight":
        argv = [strace, "-f", "-qq", "--seccomp-bpf", "-s", "65536",
                "-e", "trace=execve,execveat", "-o", str(sample / "execve.log")] + command
    elif mode == "ir":
        child_environment = dict(environment, VALGRIND_LIB=str(tools / "valgrind/usr/libexec/valgrind"),
            LD_PRELOAD=str(tools / "ohm-valgrind-env.so"), OHM_BENCH_NORMALIZE_VALGRIND_ENV="1")
        argv = command[:3] + [str(tools / "valgrind/usr/bin/valgrind.bin"), "--tool=callgrind",
            "--trace-children=no", "--extra-debuginfo-path=" + str(tools / "valgrind/usr/lib/debug"),
            "--callgrind-out-file=" + str(sample / "profile.callgrind")] + command[3:]
    else:
        assert mode == "native"
    observation = quiet.require_quiet() if native_stage else observer.sample()
    (sample / "host-before-command.json").write_text(json.dumps(observation, indent=2) + "\n")
    result = portable.run_command(argv, case / "uv", child_environment,
                                  sample / "stdout", sample / "stderr")
    (sample / "command-result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result["returncode"] == 0
finally:
    try:
        if initialized:
            fixture.restore(state)
    finally:
        portable.install_variant(backup, active)
        active.chmod(original_stat.st_mode & 0o777)
        os.utime(active, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
```

The snippet demonstrates portable invocation and cleanup, not the complete admission audit. Before scoring a fresh cohort, use the included `full_argv.trace_records()` on both excluded preflights and verify the same complete compiler-argv multiset, two ordinary source compiles and four link-only calls. Record/check the fresh fixed identities and required outputs around every arm. The helper source contains the existing full-argv comparison and strict quiet validator; use the published stage protocol for all remaining guards. Instruction observations must remain recorded without retrospective quiet filtering; native calls require strict quietness. Keep logs private until separately sanitized.

Repeat arms in the exact predeclared order from `protocol.json`, without adding retries or samples. Restore source/Cargo after every arm as above. **Only after the entire stage**, run the original uninstrumented command once and require convergence. Do not insert original-command convergence between arms: that would change cache history. For the native eight-pair stage, the excluded preflights, preparations, timed calls and final convergence total 37 commands. The published full profiles and the final-Ir accounting in `recompute.py` show how scored counts are validated; the older generic runner's header-summary count is not used.
