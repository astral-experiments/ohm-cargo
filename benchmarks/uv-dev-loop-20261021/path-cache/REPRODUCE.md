# Reproducing unit-path string caching on original PR175

This package contains two completed, separately predeclared instruction
confirmations and two completed native confirmations. It claims lower Cargo
instruction counts for fresh, full-workspace `cargo check` and
`cargo test --no-run` on unchanged uv. It does not establish a native wall-time
improvement, a dirty-build improvement, or faster test execution.

The production pair is the original PR175 revision, before the later external
restack. Later PR heads are not these reproduction inputs. Six earlier
experiments or setup attempts are also retained, including a failed profiler
smoke test and inconclusive native runs. They use different normal builds or
baselines and are never pooled with the production confirmations. See
HISTORY.md. The dated protocols remain unchanged historical inputs.

## Inspecting and reanalyzing the retained observations

Run `sha256sum -c SHA256SUMS` in this directory, then extract
`raw-results.tar.gz` into a fresh copy of the package. Its relative paths and
every uncompressed file hash are listed in `RAW-MANIFEST.json`. Extracting adds
the complete sample/subrun tables and logs to the readable result directories.
The following commands use the frozen Python stdlib runners:

```sh
python3 harness/paired.py analyze results/check-ir-confirmation --confidence 0.99 --resamples 20000 --seed 1701
python3 harness/paired.py analyze results/test-ir-confirmation --confidence 0.99 --resamples 20000 --seed 1701
python3 harness/paired_repeated.py analyze results/check-native-confirmation --confidence 0.99 --resamples 20000 --seed 1701
python3 harness/paired_repeated.py analyze results/test-native-confirmation --confidence 0.99 --resamples 20000 --seed 1701
```

Use a copy because analysis rewrites `analysis.json`. Analysis uses scalar
sample tables; it does not require the original executables or absolute log
paths. Full Callgrind attribution files are retained in the original task
workspace rather than this archive. Their `events:`, `summary:` and `totals:`
lines, exact hashes, sizes and matching sample counts are in
`callgrind-counter-extracts.jsonl`.

Read instruction results from `analysis.metrics.cargo_ir.statistics` and the
separate `instruction-gate.json`. Top-level elapsed-time results from an
instrumented run are not native timing. For native runs, a statistical unit is
one paired group of eight invocations per variant. The 480 measured invocations
per workflow are not 480 independent observations. All 32 additional warmup
invocations per workflow are retained and excluded from inference.

The gate requires at least 1% reduction, a positive lower endpoint of the 99%
paired bootstrap interval, exact two-sided sign-test p <= 0.01, and positive
effects in both AB and BA orders. Both instruction workflows pass. Both native
workflows fail the native gate. In particular, the native test-build sign test
passes, but its point estimate is below 1% and its 99% interval includes zero.
An inconclusive result does not prove absence of a regression. Do not pool
hosts, workflows, build settings, exploratory observations or profiler wall
time, and do not extend a batch or remove outliers after inspecting effects.

## Rebuilding the matched Cargo pair

The baseline source is pinned Cargo commit
`5e5d271d763d7beb38b48755e22bd59e93f02b97` plus PR175
`efc8b51502f8a8d1fe76997dc984481edde2740e`, with tree
`3d67bfb965bc0b6452ab78205045c5154db0acf7`. The candidate additionally applies
`build/candidate.patch`, yielding tree
`b0dfb3fe2cfd8d310efa04a345f58886296f712a`.

Use one physical source checkout and one build target directory for both
variants. Keep Git HEAD at the pinned commit and apply the baseline/candidate
patches as working-tree changes so the embedded Cargo commit remains identical.
Record and verify the source trees with an isolated Git index. Freeze each
linker output before replacing the working-tree patch or building tests.

The production build drivers and both provenance records in `build/` specify
the complete original command and environment. The central command was:

```sh
cargo build --release --locked --bin cargo --features all-static,ohm-defaults -j 8 -v
```

It used stock Rust 1.99.0, opt-level 3, ThinLTO, one codegen unit, debug level 1,
no incremental compilation, no linker stripping, `CFG_RELEASE_CHANNEL=dev`,
and `LIBZ_SYS_STATIC=1`. Clear the inherited overrides listed in the driver,
then set every profile/compiler/path value from the provenance with a consistent
new prefix. Ancestor Cargo configuration and native toolchain settings must be
recorded. These builds have no PGO and are not the published PGO toolchain.

The safe strip helper is workspace-layout-specific. Place a copy at
REPLICA/work/benchmark/strip_binaries.py, the unchanged linker outputs at
REPLICA/work/binaries/NAME, and a matching manifest.json in that binaries
directory with an entry for each NAME and its original_linker_output_sha256.
Pass the binary names to that script; it writes binaries/stripped/NAME and
checks allocated ELF section addresses, sizes, alignment and bytes. It is not
a generic path-argument CLI and cannot be run directly from this package's
harness directory without recreating that layout. Alternatively, call its
allocated_sections helper before and after an explicit objcopy --strip-debug
INPUT OUTPUT and compare the complete results. Never overwrite INPUT; hash
and preserve it separately. The
measured stripped baseline hash is
`63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8`;
the candidate hash is
`c060facdbaae756453968d6eaef1c5ab71c127d15c329a8453e260ef3064c583`.
The original linker-output hashes are in the build/strip records. Executables
are not embedded in this text evidence package or made downloadable by these
historical local paths. Rebuilt binaries receive their actual new hashes and
need a new paired experiment; identical absolute counts are not assumed.

## Preparing a new workspace prefix

Use uv commit `3d82a6ad5a7eab8c68236553b7846517767c4b61` with clean tracked
files and lockfile SHA256
`747296375bb1889689f3bbb1e0303bddd071d6a65117c00be50856448260d014`.
The workload compiler is the published Ohm 1.99.0-6 rustc, distinct from the
stock compiler used to build the Cargo pair. Its binary and driver identities
are recorded in each original manifest and `INPUTS.json`.

The original instruction and native configurations use different absolute
roots/layouts. Create a fresh replica root for the chosen configuration and
map its historical root once. Copy metadata/source inputs into the resulting
locations using the hash-based package locations in `INPUTS.json`; provision
external compiler, runtime, binary and system-tool inputs separately. Preserve
all historical metadata bytes. Rewrite only a copied runnable configuration
and record the diff plus the new input hashes. Do not blindly run the original
workspace-specific orchestration or production-build drivers at a new prefix.

```sh
python3 - ORIGINAL.json REPLICA.json OLD_ROOT NEW_ROOT <<'PY'
import json, os, sys
from pathlib import Path
source, destination, old, new = sys.argv[1:]
old = old.rstrip(os.sep)
new = str(Path(new).expanduser().resolve())
assert old and old != os.sep and new != os.sep
def relocate(value):
    if isinstance(value, dict):
        return {key: relocate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [relocate(item) for item in value]
    if isinstance(value, str):
        return new if value == old else value.replace(old + os.sep, new + os.sep)
    return value
config = relocate(json.loads(Path(source).read_text()))
config['env']['CARGO_HOME'] = str(Path(new) / 'cargo-home')
config['env']['PATH'] = str(Path(config['env']['RUSTC']).parent) + ':/usr/bin:/bin'
fixed = [config['cwd'], config['canonical_executable']]
fixed += [config['env'][key] for key in ('CARGO_HOME', 'CARGO_TARGET_DIR',
          'CARGO_BUILD_BUILD_DIR', 'RUSTC', 'RUSTDOC')]
assert all('{' not in value for value in fixed)
with Path(destination).open('x') as stream:
    json.dump(config, stream, indent=2)
    stream.write('\n')
PY
```

This snippet prepares configuration only; it is not an executed replication.
Inspect all resolved paths and `record_files`. Replace historical preflight
and configuration records with newly generated replica records, adding hashes
for the actual profiler/system tools. Preserve the old metadata separately.
Do not copy personal credentials or configuration from the historical Cargo
home. Record trust-store/runtime differences as a new-environment replication.

Both variants must run at one regular, non-symlink canonical Cargo path. The
runner atomically replaces its bytes before each sample. Do not switch symlinks
or execute the immutable input binaries at different paths. Within a pair,
keep the same uv path, compiler, rustdoc, Cargo home, target directory, shared
build cache, command, job count, affinity and build-affecting environment.
Only the immutable input binary and output-log/profile names distinguish the
variants. `{cargo}` must resolve to the same absolute path each time.

Seed new build artifacts at the new prefix using the canonical Cargo path and
final environment. Do not transplant target/shared-cache state: build-script
outputs, provenance and fingerprints contain absolute paths. Registry archives
and index data may be reused; generated state must be freshly produced.
Fetch dependencies outside measurement, then use `--locked --offline`.
The exact workload commands are full-workspace check and test-build, with
`-Zohm-defaults=yes`, eight jobs and CPUs 0-7 as recorded in the configurations.
`cargo test --no-run` must never execute uv's tests.

Warm both variants, capture an untimed native `strace -f -e trace=execve`, and
require successful fresh output with no rustc, linker, build-script or test
child. Retain traces and scan every later preparation/warmup/measured log for
unexpected compilation. Check source/input hashes before and after. Run in
the ordinary host environment with the host quiet: this task's sandbox changed
root ownership and thereby disabled Ohm's trusted shared cache. Do not change
host security settings to obtain a benchmark.

## Running new fixed batches

Use new output directories. Freeze the configurations, source/binary/runtime
hashes, seeds and acceptance rules before starting. The original instruction
seeds were 2026102128 for check and 2026102129 for test-build; native seeds were
2026102126 and 2026102127. The following illustrates check; use the separate
test configuration and its declared seed for the other workflow.

```sh
python3 harness/paired.py run --config REPLICA_CHECK_IR.json --output NEW_CHECK_IR \
  --phase confirmation --pairs 12 --warmup-pairs 2 --seed 2026102128
python3 harness/paired.py analyze NEW_CHECK_IR --confidence 0.99 --resamples 20000 --seed 1701
python3 harness/paired_repeated.py run --config REPLICA_CHECK_NATIVE.json --output NEW_CHECK_NATIVE \
  --phase confirmation --pairs 30 --warmup-pairs 2 --seed 2026102126
python3 harness/paired_repeated.py analyze NEW_CHECK_NATIVE --confidence 0.99 --resamples 20000 --seed 1701
```

Counter configuration retains Callgrind 3.22, `--trace-children=no`, the
environment-normalization shim, and explicit normal system certificate paths.
The shim removes profiler-injected loader variables before Cargo/children;
its source and original library hash are included. Compile a replica shim with
`cc -shared -fPIC -O2 -o ohm-valgrind-env.so ohm-valgrind-env.c -ldl`, record its
actual hash, and use the correct absolute paths in the copied configuration.
Keep `VALGRIND_LIB` and extra debuginfo pointed at the same installation.
Native configuration omits all profiler injection.

Counts cover Cargo userspace instructions only, excluding compiler, linker,
build-script, test and kernel work. Both variants report Valgrind's brk limit
and allocator fallback; the raw stderr is retained. Its instruction attribution
does not establish the effect of the native allocator or a wall-time speedup.

See `VALIDATION.md` for the exact correctness scope, binary distinctions,
retained failures and supported test environments. The archived failed smoke
invocation is diagnostic data only; it must not be included in any analysis.
