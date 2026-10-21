# Build-output remap: private review evidence and reproduction

The proposed change skips searching each build-script output value when the old
and current output-directory strings are byte-for-byte equal. Real relocation
still takes the existing replacement path. The measured source tree is
`1df4917fb98e449198b61c502b799793d9aabffb`: pinned Cargo
`5e5d271d763d7beb38b48755e22bd59e93f02b97`, upstream PR175, and only this change.
uv remains unchanged at `3d82a6ad5a7eab8c68236553b7846517767c4b61`.

The completed 12-pair check confirmation gives **3.657684% fewer Cargo
instructions**, 99% interval **3.630245%–3.684516%**, 12 wins, exact two-sided
sign-test p=0.00048828125, with both execution orders positive. The independent
30-pair native check confirmation is inconclusive: 2.459% estimated reduction,
99% interval -5.509%–10.141%, p=0.5847. Make an instruction-count claim only.
The independent 30-pair native test-build confirmation is also inconclusive:
0.6548% estimated reduction, 99% interval -2.3905%–3.8403%, 21 wins and 9 losses,
p=0.042774. All 2,597 native result files have been transferred and verified.
The fixed test-build instruction confirmation is still running; append its
completed evidence before describing that workflow's instruction result.

The adjacent `first-pr-evidence-index.json` lists the immutable identities,
completed evidence, retained negative results, and correctness attempts. It is
an inventory, not a seal of still-running results.

## What belongs in the private evidence branch

- Preserve the frozen runners together, with their original filenames:
  `paired.py` SHA256 `50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf`
  and `paired_repeated.py` SHA256 `50547460e030aa73e1f48121bf477cf8f4a4538bf1bb577851af54176750b6d3`.
  Include their existing tests and the dated protocols; do not revise historical
  protocols after seeing results.
- Include each original configuration, manifest, complete raw sample table,
  analysis JSON, warmup observations, preparation logs, stdout/stderr and
  freshness/exec-trace evidence. Native groups also need all raw subrun tables
  and their logs. Include failed attempts and explicit external-priority holds.
- For every Callgrind file, include its `events:` and `summary:` extraction,
  original SHA256 and sample identity. The complete attribution profiles remain
  retained separately; say explicitly if the branch contains only extracts.
  Scalar measurements can be independently reanalyzed from the complete tables.
- Bind both measured binaries to their build/strip metadata, exact source
  patches, build driver and provenance. Keep binary downloads in private
  artifacts or provide the recorded rebuild recipe; do not invent a download
  URL or imply local-only binaries are already downloadable.
- Record compiler/driver hashes, uv lockfile and commit, CA bundle, resolved
  runtime libraries, Valgrind and the environment-normalization shim, host and
  affinity, relevant inherited build settings and Cargo configuration. Preserve
  historical metadata bytes, including their historical absolute paths.

The baseline stripped CLI is
`63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8`;
the candidate is
`2805f47db54fbd35e4218c1ce232861aa7e8c6efede1684ccce8e999d5cf03f3`.
These use `all-static,ohm-defaults`, ThinLTO, one codegen unit, opt-level 3,
debug level 1, and the dev release channel, compiled with stock Rust 1.99.0.
They have no PGO and are not the published PGO toolchain. Debug-only stripping
preserved every allocated ELF section's address, size, alignment and bytes.

For a source rebuild, use one physical source directory and one target
directory for both variants. Keep Git HEAD at the pinned commit and apply
PR175, then the candidate patch, as recorded working-tree changes so the
embedded Cargo identity is the same. Preserve the exact command, compiler,
features and profile environment in `provenance-pr175.json`. Freeze both linker
outputs before any correctness-test build. Rebuilt binaries get new hashes;
verify the two expected source trees and repeat the paired experiment rather
than treating their absolute counts as the original measurements.

## Reproducing at another workspace prefix

Choose a fresh absolute root for each experiment. Preserve that experiment's
relative asset layout and map its historical root to the new root **once**.
Counter and remote-native configurations have different historical layouts;
they may use separate replica roots. Copy immutable inputs into the matching
locations. Rewrite only the copied runnable JSON configuration, not historical
manifests or metadata. Keep the old and new configuration and a recorded diff.

For the first PR's fresh-workload configurations, this config-only recipe
performs the prefix mapping and chooses a private Cargo home. Run it with the
historical root from the selected manifest and a new output configuration:

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

This snippet is a packaging recipe, not an executed benchmark. Inspect the
resolved configuration before use. Its deliberate PATH/Cargo-home changes must
be recorded. Resolve and hash the actual system tools, trust store and runtime
libraries on the new host; differences make this a new-environment replication,
not a byte-identical replay. Record any ancestor Cargo configuration and reject
unaccounted build overrides. Do not copy personal credentials or configuration
from the original Cargo home.

The following invariants are essential:

1. Both variants execute at one regular, non-symlink canonical Cargo path.
   The frozen runner copies executable bytes there before every sample. Do not
   select variants with different executable paths or by switching symlinks.
2. Within each pair, uv source, compiler/rustdoc, Cargo home, target directory,
   shared build cache, flags, jobs, affinity and build-affecting environment
   are identical. Only immutable input-binary locations and output log/profile
   names distinguish the variants. `{cargo}` resolves to the same path.
3. **Seed new uv artifacts at the new prefix.** Never transplant the old target
   or shared build cache. Stored build-script output directories can retain the
   old prefix, turning the identity-remap workload into actual relocation.
   Registry archives/index data may be reused; generated artifacts, expanded
   build state, provenance, dep-info and runlists must be freshly produced.
4. Seed through the same canonical Cargo path and final environment. Fetch
   dependencies outside measurement, then use `--locked --offline`. Check uv's
   commit and clean status before and after. Both workflows are full-workspace
   commands; test-build means `cargo test --no-run`, never running uv tests.
5. Before timing, warm both variants and retain an exec trace demonstrating
   freshness. No measured invocation may compile/check a package or launch
   rustc/linkers/build scripts. The repeated runner enforces fresh group output;
   retain a complete log scan and the untimed trace as additional evidence.
6. Keep the host quiet and execute in the ordinary host environment. The task's
   sandbox remapped root ownership and disabled Ohm's trusted shared cache.
   Record process/root ownership; do not alter security settings to benchmark.

Run the frozen core for counters and the frozen repeated adapter for native
timing. Use new result directories, two recorded warmup pairs, and the sample
count/seed committed before starting. The original check counter seed is
`2026102118`; a replication may predeclare a new seed. Native configurations
use `repetitions: 8` and `repeatable_workload: "noop"`.

```sh
python3 paired.py run --config REPLICA_IR.json --output NEW_IR_RESULTS \
  --phase confirmation --pairs 12 --warmup-pairs 2 --seed 2026102118
python3 paired.py analyze NEW_IR_RESULTS --confidence 0.99 --resamples 20000 --seed 1701
python3 paired_repeated.py run --config REPLICA_NATIVE.json --output NEW_NATIVE_RESULTS \
  --phase confirmation --pairs 30 --warmup-pairs 2 --seed PREDECLARED_SEED
python3 paired_repeated.py analyze NEW_NATIVE_RESULTS --confidence 0.99 --resamples 20000 --seed 1701
```

Callgrind must retain `--trace-children=no`, the recorded shim and explicit
certificate defaults. Counts cover Cargo userspace instructions only, excluding
rustc, linkers, build scripts, tests and the kernel. Both variants encountered
Valgrind 3.22's brk limit and allocator fallback; retain that caveat. Never use
Callgrind elapsed time as a native timing result. Native configurations omit
the profiler and its injected loader environment.

Read counter results from `analysis.metrics.cargo_ir.statistics`; the top-level
Callgrind wall-time screen is not a counter acceptance decision. The fixed
counter gate is at least 1% reduction, positive 99% interval, exact two-sided
sign p<=0.01, and positive estimates in both AB/BA groups. Native inference uses
30 paired group sums, not 480 independent invocations, with the same gates.
Keep exploratory and confirmatory results separate. Do not remove slow samples,
extend a batch after seeing its p-value, pool hosts, or claim that an
inconclusive interval establishes no regression.

## Correctness record and publication scope

The exact measured candidate CLI passed all 15 existing parser/relocation
integration cases using the supported classic-defaults override. The immutable
CLI was executed by a recorded test-only launcher at the prebuilt harness's
baked Cargo path. The launcher restores the actual production dev channel and
sets `__CARGO_OHM_DEFAULTS=no`; the harness otherwise forces stable and ignores
that inherited option. The compiler was the pinned Ohm rustc selected through
PATH, with RUSTUP_TOOLCHAIN removed. This is classic-defaults parser coverage,
not a claim that all 15 snapshots support Ohm-enabled verbose compiler flags.

The preceding Ohm-enabled attempt passed 11 cases, including target relocation;
four verbose-command snapshots differed because of the injected Ohm flags.
The first attempt selected stock rustc and failed at unsupported compiler
options before exercising the parser. Both attempts and their complete logs
are retained. Earlier original-base coverage also retains the unavailable-i686
target failure and its 15-case supported rerun. No expected snapshot or Cargo
source was changed to obtain a pass.

`python3 work/benchmark/validate_build_output_production.py --lease-granted --mode classic`
is the exact successful invocation; its frozen SHA256 is
`abd95160f8a721ca727b2d7cc047d6de0fd653b75c5541a13f3b7e1ee47fb699`.
Its report binds the CLI, harness, compiler and input hashes, records all test
names, and confirms atomic restoration of the original test entry, including
inode, mode and mtime. The original source diff remained unchanged, and no
Cargo/rustc/testsuite process remained when the local test lease ended. This
helper targets the recorded prebuilt harness and assumes its original script
placement under `work/benchmark/`; the frozen copy preserves its source. For
correctness replication at a new prefix, rebuild that harness there and record
its actual baked Cargo path. Copying a prebuilt test executable does not rebase
its embedded path. The benchmark runners themselves use explicit configuration
paths and do not depend on that test-harness mechanism.

Before sealing the branch, add the completed test-build instruction result,
verify the final artifact inventory, and link the evidence commit
from the draft source PR. State the measured workload, exact source/binary
identities, instruction scope, native timing uncertainty and validation
limitations in the PR. Nothing in this plan publishes artifacts or changes
the candidate source.
