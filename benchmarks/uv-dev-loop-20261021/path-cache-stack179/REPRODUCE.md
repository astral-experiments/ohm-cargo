# Reproducing the restacked path comparison

This package measures current PR179 commit `19718e6d…` against the ported path
cache at `c40676e2…`. Use the exact trees in README.md and the bundled patches;
later branch heads are different inputs. The original PR175 measurements remain
separate. No sample, native result, or cumulative result is pooled into this
comparison.

## Reanalyze the retained observations

Verify the package, then extract the archive into a fresh copy of this
directory. Its regular relative members and uncompressed hashes are listed in
`RAW-MANIFEST.json`. Use a copy because analysis rewrites `analysis.json`.

```sh
sha256sum -c SHA256SUMS
tar -xzf raw-results.tar.gz
python3 harness/paired.py analyze results/check-ir-confirmation --confidence 0.99 --resamples 20000 --seed 1701
python3 harness/paired.py analyze results/test-ir-confirmation --confidence 0.99 --resamples 20000 --seed 1701
```

The analyzer needs only Python's standard library and the scalar sample tables;
it does not execute Cargo or need the original absolute log paths. Read
`analysis.metrics.cargo_ir.statistics`. Top-level times from the instrumented
run are not native timing. The full attribution profiles are not in the
archive; `callgrind-counter-extracts.jsonl` preserves their `events:`, `summary:`
and `totals:` lines, sample mapping, size and SHA256. All other run files,
including raw JSON/CSV, warmups, preparation logs and stdout/stderr, are retained.

Each workflow has 12 paired observations after 2 warmup pairs. The balanced
randomized orders contain six AB and six BA pairs. The point estimate is
`1 - exp(-mean(log(baseline_count / candidate_count)))`. The 99% percentile
interval resamples whole paired log-ratios 20,000 times with seed 1701.
The exact two-sided sign test uses non-tied pairs. The acceptance rule requires
at least 1% point reduction, a strictly positive 99% lower bound, sign p<=0.01,
and positive geometric effects in both orders. Both workflows pass. No outlier
removal, extensions, interim effect inspection, or pooling was used.

## Rebuild matched Cargo binaries

The build cohort starts at pinned Cargo HEAD
`5e5d271d763d7beb38b48755e22bd59e93f02b97`. Apply
`build/frozen/stack179-current.patch` or
`build/frozen/stack179-path-cache.patch` as complete working-tree patches at that
HEAD. Do not apply one full patch on top of the other. The former yields tree
`f4ce59f92aa17461fe3c8b68923c88539136045a`; the latter yields
`0a392258c801cff734d223a3f9af73d5b5a4e3c0`. The separate incremental
`build/path-cache-stack179.patch` describes just the candidate change.

Use one physical source checkout and one target directory sequentially for both
builds. Keep embedded HEAD fixed, verify trees with an isolated Git index, and
freeze each original linker output before switching source or building tests.
The frozen cohort driver, shared provenance, all three variants' build/strip
records and actual compiler command logs are included. The central command is:

```sh
cargo build --release --locked --bin cargo --features all-static,ohm-defaults -j 8 -v
```

Use the recorded stock Rust 1.99.0 build compiler, opt-level 3, ThinLTO, one
codegen unit, debug level 1, incremental=false, no linker stripping,
`CFG_RELEASE_CHANNEL=dev`, and `LIBZ_SYS_STATIC=1`. Clear inherited overrides
and set the remaining exact profile/tool/path values from
`build/results/provenance.json` and the driver. Record ancestor Cargo config and
native toolchain inputs. There is no PGO. Do not blindly execute the original
host- and workspace-specific build or measurement orchestration at a new root.

The safe strip helper is workspace-layout-specific: place it at
`REPLICA/work/benchmark/strip_binaries.py`, original linker outputs at
`REPLICA/work/binaries/NAME`, and `manifest.json` in that binaries directory
with each NAME's `original_linker_output_sha256`. Pass names, not arbitrary
paths, to the helper. It writes `binaries/stripped/NAME` and verifies all
allocated ELF section addresses, sizes, alignment and bytes. Alternatively,
compare its `allocated_sections` results before/after an explicit
`objcopy --strip-debug INPUT OUTPUT`, preserving and hashing INPUT separately.
Executables are not included in this evidence package. Rebuilt binaries get
their actual new hashes and require a new experiment; identical absolute
instruction counts are not assumed.

## Prepare one consistent new workspace prefix

Pin unchanged uv to `3d82a6ad5a7eab8c68236553b7846517767c4b61`, with lockfile
SHA256 `747296375bb1889689f3bbb1e0303bddd071d6a65117c00be50856448260d014`.
Use the published Ohm 1.99.0-6 workload compiler, distinct from the stock compiler
that built Cargo. Its rustc/driver hashes are in the original manifests and
`INPUTS.json`. Provision registry sources, the compiler, Callgrind 3.22, system
tools and trust store separately.

Copy the relevant configuration from `configs/`, then map its historical root
once to your replica root. Copy unchanged evidence inputs to their mapped
locations using `INPUTS.json`'s hash-to-package mapping. Preserve the original
metadata bytes; only a copied runnable config and new preflight/seal records
should describe the replica. A configuration-only relocation example is:

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

Inspect every resolved path, profiler/shim path, environment field and
`record_files` entry. Replace historical runnable-config/preflight/seal records
with the replica's new records and hashes; keep historical metadata separately.
Record the diff and actual binary/runtime identities. Do not copy personal
credentials or config from the historical Cargo home. Trust-store and runtime
differences make this a new-environment replication.

Both variants must run at the same regular, non-symlink canonical Cargo path.
The harness atomically copies each immutable variant there before its sample.
Do not execute the two inputs directly at different paths or switch symlinks.
Within every pair, keep uv, rustc/rustdoc, Cargo home, target/shared-cache paths,
command, environment, jobs and affinity identical. Only the immutable input
binary and log/profile output names distinguish variants.

Seed fresh generated artifacts at the new prefix using the canonical Cargo
path. Do not transplant target or shared-cache state containing old absolute
paths. Registry archives/index data may be reused. Fetch outside measurement,
then use `--locked --offline`. The exact workloads are:

```sh
cargo -Zohm-defaults=yes check --locked --offline -j 8
cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8
```

These are full-workspace commands, with CPUs 0-7 and eight jobs in the config.
Warm both variants and capture untimed native `strace -f -e trace=execve` output.
After seeding, require successful fresh output and no compiler, linker,
build-script or test children. Retain traces and scan all later preparation,
warmup and measurement logs for unexpected compilation. Verify inputs and clean
uv before/after. Use the ordinary quiet host environment: this task's sandbox
changed root ownership and disabled Ohm's trusted shared cache.

Compile the included loader-environment shim with
`cc -shared -fPIC -O2 -o ohm-valgrind-env.so ohm-valgrind-env.c -ldl` and record
its actual hash. Preserve `--trace-children=no`, `VALGRIND_LIB`, extra debuginfo
and the explicit normal system `SSL_CERT_FILE`/`SSL_CERT_DIR` settings from the
counter configuration. The shim removes profiler-injected loader variables;
certificate verification remains enabled.

## Run newly sealed fixed batches

Freeze the source/binary/runtime hashes, both configurations, seeds and gates
before running. Use new output directories. Original path seeds are 2026102161
for check and 2026102162 for test-build:

```sh
python3 harness/paired.py run --config REPLICA_CHECK_IR.json --output NEW_CHECK_IR --phase confirmation --pairs 12 --warmup-pairs 2 --seed 2026102161
python3 harness/paired.py analyze NEW_CHECK_IR --confidence 0.99 --resamples 20000 --seed 1701
python3 harness/paired.py run --config REPLICA_TEST_IR.json --output NEW_TEST_IR --phase confirmation --pairs 12 --warmup-pairs 2 --seed 2026102162
python3 harness/paired.py analyze NEW_TEST_IR --confidence 0.99 --resamples 20000 --seed 1701
```

Audit successful/fresh logs and immutable inputs before analyzing each complete
batch. Use the frozen gate in `historical/harness/run_followon_ir-d78f4b06a398.py`
as the acceptance definition. Its original orchestration paths are historical;
the standalone harness commands above are the portable execution interface.
Do not interpret profiler wall time as native timing or extend batches after
seeing effects. The other two configurations/protocols in this package are
included because the shared input seal covered a distinct cumulative
experiment; they do not add observations to this path comparison.
