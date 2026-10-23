# Rebuild and rerun

The numerical replay needs Python 3 only:

```sh
python3 reproduce.py --profiles profiles
```

It checks the final `Ir` total against every disjoint self-cost and retained stderr counter, then recomputes the exact two fixed block statistics. Full raw profile records are retained apart from declared command/path substitutions. Private preflight, environment and restoration validation is not reconstructed by this replay.

## Matched Cargo builds

Use an owned Linux x86_64 directory and the SDK12 bundle whose SHA256 is in `source-identities.json`. Install it privately with its normal installer; keep global rustup/configuration unchanged. Obtain the authorized Ohm Cargo repository in a fresh owned checkout. Keep the common embedded HEAD at `fdd26156be98618e2e01a9e02703edac71b79a35`, with the published parent `bca8c1077b2b40b4b037edc059333d7d98f91bae` staged as the baseline source. Keep both builds at the same physical source/cache/target paths. The exact retained settings are:

```sh
export CARGO_HOME="$build_root/cargo-home"
export CARGO_TARGET_DIR="$build_root/target"
export RUSTC="$sdk_root/bin/rustc"
export RUSTDOC="$sdk_root/bin/rustdoc"
export CARGO_INCREMENTAL=0
export CARGO_PROFILE_RELEASE_INCREMENTAL=false
export CARGO_PROFILE_RELEASE_OPT_LEVEL=3
export CARGO_PROFILE_RELEASE_LTO=thin
export CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
export CARGO_PROFILE_RELEASE_DEBUG=1
export CARGO_PROFILE_RELEASE_STRIP=none
export CFG_RELEASE_CHANNEL=dev
export LIBZ_SYS_STATIC=1
cd "$build_root/source"
git checkout --detach fdd26156be98618e2e01a9e02703edac71b79a35
git read-tree --reset -u bca8c1077b2b40b4b037edc059333d7d98f91bae
test "$(git write-tree)" = 90af39c2cab717940d5b09c1a4add2aaa02734e1
"$sdk_root/bin/cargo" -Zohm-defaults=no build --release --locked --offline \
  --bin cargo --features all-static,ohm-defaults -j 24 \
  --message-format=json-render-diagnostics -v
cp "$CARGO_TARGET_DIR/release/cargo" "$build_root/baseline-linked"
objcopy --strip-debug "$build_root/baseline-linked" "$build_root/baseline"
git apply --index "$evidence_root/candidate.patch"
test "$(git write-tree)" = c688d8d2232d1b8bb776d589a5fdb6218df7af38
"$sdk_root/bin/cargo" -Zohm-defaults=no build --release --locked --offline \
  --bin cargo --features all-static,ohm-defaults -j 24 \
  --message-format=json-render-diagnostics -v
cp "$CARGO_TARGET_DIR/release/cargo" "$build_root/candidate-linked"
objcopy --strip-debug "$build_root/candidate-linked" "$build_root/candidate"
```

Seed only locked dependency archives/indexes before these offline builds. Preserve linked outputs and verify allocated ELF sections after stripping. Record the actual C/C++/link tools, SDK files, source trees, commands and configuration. The original binary hashes identify this pair, not every reproducible build on another system. Run the two selectors listed in `source-identities.json` before measuring: the five graph tests and 24 existing lockfile-compatibility tests. Preserve failures and ignored cases.

## Fresh workload admission

Create a fresh checkout of uv `3d82a6ad5a7eab8c68236553b7846517767c4b61`, a common private active Cargo path, and independent per-arm `target`, `shared` and `package-home` banks. Import archive/index seeds only; warm each arm independently. Use the common SDK12 runtime and record every ancestor `.cargo/config{,.toml}` observation, including absent files. Do not carry the compiler-build `CARGO_INCREMENTAL=0` setting into the uv workload: the measured uv environment left it unset.

Use a controlled environment with `CARGO_BUILD_JOBS=8`, `CARGO_TERM_COLOR=never`, `CARGO_TARGET_DIR=$study_root/target`, `CARGO_BUILD_BUILD_DIR=$study_root/shared`, `CARGO_HOME=$study_root/package-home`, explicit common `RUSTC`/`RUSTDOC`, and `PATH=$study_root/bin:$study_root/runtime/bin:/usr/bin:/bin`. Native commands have `LD_PRELOAD` and `LD_LIBRARY_PATH` unset. Set `OHM_BENCH_NORMALIZE_VALGRIND_ENV=1` and `VALGRIND_LIB=$profiling_root/valgrind/usr/libexec/valgrind` in both native and profiled contexts. Keep HOME unchanged. Create the already-selected task-owned `TMPDIR` as a private directory before profiling; the original setup caught its absence before a valid cohort began.

The supplied `ohm-valgrind-env.c` is the exact parent-only adapter source. Use the recorded binary/tool identities, or build it with the matching Valgrind headers and record new identities. The adapter removes Valgrind's loader variables in Cargo before child environment inspection. A fresh native/profile exec trace must prove child parity; the adapter alone is not that proof. The supplied `env_trace.py` is the existing robust exec parser.

Before any block, verify native freshness and native/profile dirty parity for both arms. Check must execute exactly one ordinary uv-library rustc and no rustdoc/test program; preserve each ordered argv and complete environment, omitting only the dead `CARGO_MAKEFLAGS` descriptor string for comparison. Require exact output identity and Cargo diagnostics after removing only the variable `Finished ... in ...` duration. This study admitted one complete check-metadata hash per arm after identical released SDK12 `rustc -Zls=all` listings and a full reconstruction of every changed byte: three two-record swaps, a two-record relocation with relative-offset rebasing, and two associated index-field changes (56 differing bytes total). The measured guard accepted only those finite complete hashes; no general metadata mask was used. A new fixture must establish its own artifact/output/context hashes and, if needed, an equally bounded proof before any sample. Historical hashes, inode/mtime values or serialization offsets cannot be reused as admission.

## One arm's collection step

Run the controller on CPU 8 (`taskset -c 8 bash sample.sh`) and workload children on CPUs 0–7. Set task-specific `study_root`, `evidence_root`, `profiling_root`, `tracer`, `selected_cargo`, `sample_root`, `block_root` and `pair_index` before this example. Activate the selected arm's independently warmed private state bank at the common paths first. A fixed block has one 30-second entry settle, not a per-sample sleep.

```sh
set -eu
umask 077
active="$study_root/bin/cargo"
state="$sample_root/fixture"
mkdir -p "$sample_root"
test -f "$active"
test ! -L "$active"
cp -p "$active" "$sample_root/original-cargo"
python3 "$evidence_root/dirty_fixture.py" init --state "$state" \
  --source "$study_root/uv/crates/uv/src/lib.rs" --workspace "$study_root/uv" \
  --baseline-target "$study_root/target" --candidate-target "$study_root/unused" \
  --shared-build-dir "$study_root/shared"
cleanup() {
  prior_status=$?
  restore_status=0
  python3 "$evidence_root/dirty_fixture.py" restore --state "$state" || restore_status=$?
  cp -p "$sample_root/original-cargo" "$active" || restore_status=$?
  if [ "$prior_status" -ne 0 ]; then exit "$prior_status"; fi
  exit "$restore_status"
}
trap cleanup EXIT
cp "$selected_cargo" "$active"
chmod --reference="$sample_root/original-cargo" "$active"
python3 "$evidence_root/dirty_fixture.py" prepare --state "$state" \
  --batch "$block_root" --stage measurement --pair "$pair_index" --variant baseline -- \
  taskset -c 0-7 "$active" -Zohm-defaults=yes check --locked --offline -j 8 \
  >"$sample_root/before.stdout" 2>"$sample_root/before.stderr"
cd "$study_root/uv"
LD_PRELOAD="$profiling_root/ohm-valgrind-env.so" \
  "$tracer" -f -qq --seccomp-bpf -v -s 65536 -e trace=execve,execveat \
  -o "$sample_root/exec.trace" taskset -c 0-7 \
  "$profiling_root/valgrind/usr/bin/valgrind.bin" --tool=callgrind \
  --trace-children=no --demangle=no \
  --extra-debuginfo-path="$profiling_root/valgrind/usr/lib/debug" \
  --callgrind-out-file="$sample_root/profile.%p.callgrind" \
  "$active" -Zohm-defaults=yes check --locked --offline -j 8 \
  >"$sample_root/after.stdout" 2>"$sample_root/after.stderr"
```

`--variant baseline` here is the fixture helper's common-path slot, independent of the selected Cargo arm. The helper performs one excluded BEFORE warm command and an equal-length AFTER edit. Require that only uv compiled in both calls. The trap attempts source bytes/mode restoration and always restores active Cargo bytes/mode/mtime even if source cleanup fails. It does not restore source mtime. Park the selected bank afterward. This standalone example restores active Cargo at exit; the accepted block collector instead installs the next selected arm without an intervening Cargo invocation. Do not add original-source convergence between arms: at block end the collector converges each arm on the original source once, traces zero compiler launches on the following fresh command, then restores the published original Cargo.

Repeat exactly the two eight-pair schedules and seeds in `protocol.json`. Authenticate all raw records, successful exits, source/lock/Cargo restoration, output/context parity and all 16 profile totals before comparing a block. Host observations are retained without activity-based filtering. Stop that endpoint on its first valid gate failure; do not extend samples. This example collects one arm and does not automate those cohort admission/validation gates. No native timing claim follows from instrumented elapsed time.
