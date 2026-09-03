# Incremental cache expiry experiment

This experiment builds the real Ruff parser with three development-profile debug
levels. The configurations accumulate distinct incremental caches under one shared
build directory. It then exercises explicit expiry, checks that fresh artifacts
still work, and measures the next-edit cost of revisiting an expired configuration.

Build the prototype Cargo with its `ohm-defaults` feature before running:

```sh
python3 benches/incremental-gc/run.py \
  --cargo /absolute/path/to/prototype/cargo \
  --source /Users/charliemarsh/code/oss/ruff \
  --source-rev HEAD \
  --output /private/tmp/codex-cargo-targets/cargo/isolated/incremental-gc/results
```

The script requires Python 3.12 or later and the `ohm` Rust toolchain. It creates a
clean Git archive at the requested revision, leaving the source checkout unchanged.
All experimental source and build outputs live below the specified output directory;
the script rejects a nonempty directory and paths outside the bounded experiment
root. It reuses `/private/tmp/codex-cargo-home` for public registry downloads. The
trusted procedural-macro and native-tool cache options are enabled for this local
experiment.

The experiment:

1. Builds `ruff_python_parser` with `profile.dev.debug=0`, `1`, and `2`, using the
   same source path, compiler, target directory, and shared build directory.
2. Sets ownership markers to 40 days ago, **simulating age**, then runs a completely
   fresh debug=2 build. Its markers must update despite there being no compilation.
3. Runs `cargo -Zohm-incremental-gc clean incremental --max-age '30 days'` first
   with `--dry-run`, then without. The dry run must leave payloads unchanged; actual
   collection must remove exactly the stale units and preserve retained payloads.
4. Checks that both retained and expired configurations still build without invoking
   rustc. Incremental state can be removed without deleting their finished artifacts.
5. Measures the same small source edit with and without a saved baseline cache for
   debug=0, using retained/expired/expired/retained followed by
   expired/retained/retained/expired ordering. Before each trial, an unmeasured build
   restores the baseline source and artifacts; this ensures Ohm's checksum freshness
   sees a real source change every time. Each trial then restores or removes that
   same cache at the same path, leaves dependencies fixed, and must compile exactly
   the selected package once. The edit changes an added constant from zero to one;
   it does not replace the real package with a synthetic crate.

`result.json` records byte savings, invariants, individual timing samples and
medians. `provenance.json` pins the source revision and compiler/Cargo executable
SHA-256 hashes, plus Cargo's base revision, tracked diff and untracked source file
hashes. `commands/` contains exact command lines, controlled environment
values, stdout, stderr, Cargo artifact freshness records, and a rustc-wrapper log
that distinguishes compilation from compiler queries. The wrapper applies only to
workspace crates so registry sharing remains enabled, and preserves inherited build
lock descriptors. Artifact records independently check freshness for every crate.
The numbered snapshots
record every owned unit's marker, payload digest and size.

Byte measurements distinguish logical file sizes from allocation estimates and
deduplicate hardlinks by inode. They describe the managed incremental tree, excluding
the baseline backup and finished build artifacts. They do not measure APFS shared
extents or promise equivalent device free-space changes. Timing measures a single
package on the current machine; use the individual counterbalanced samples rather
than treating its ratio as a general build-speed result. Age-based collection trades
the space used by infrequently visited configurations for their next-edit latency.

The output directory is deliberately retained as evidence. It contains disposable
source archives, build artifacts and a cache backup; remove it only when the run is
no longer needed and no process is using it.

## Current release expiry result: macOS arm64

The September 3, 2026 run used Ruff revision
`0a5ec91697d9d3267392b471580c67e694b9e318`, Ohm 1.98.0-8, and the fixed
release Cargo executable. The [expiry receipt](results/expiry-release-macos-aarch64.json)
preserves source and executable hashes, per-unit payload digests, cleanup output,
measured compiler arguments, artifact freshness, and all eight timing samples.

Three debug configurations produced 15 caches across five workspace crates. After
simulating 40 days of inactivity and refreshing debug=2, the 30-day collection
removed the ten caches belonging to debug=0 and debug=1:

| Managed incremental state | Before | After |
| --- | ---: | ---: |
| Configuration caches | 15 | 5 |
| Files | 786 | 262 |
| Logical size | 349.42 MiB | 128.05 MiB |
| Allocated size, deduplicated by inode | 353.02 MiB | 129.14 MiB |

The reduction was **221.37 MiB of logical data, or 63.4%**. Allocation estimates
fell by 223.88 MiB; these are not physical free-space measurements and do not
account for shared APFS extents. The dry run changed no snapshot fields. All five
retained caches were unchanged. Both configurations tested immediately after
collection (debug=2 and debug=0) reported all 97 artifacts fresh and performed no
compilation.

Next-edit timings were collected with the earlier release Cargo executable,
before the final hash-container and worktree-trash-discovery changes. The receipt
records that executable separately; the collection checks above were repeated
with the final executable used by the tracking benchmark below. Both runs use the
same Ohm compiler and pinned Ruff source.

Each measured next edit compiled only `ruff_python_parser`, with 96 other artifacts
fresh. The expired configuration took longer in both counterbalanced blocks:

| Sample order (A = retained, B = expired) | Retained median rustc time | Expired median rustc time |
| --- | ---: | ---: |
| ABBA | 0.246 s | 0.921 s |
| BAAB | 0.243 s | 0.902 s |

The pooled medians were 0.244 s retained and 0.903 s expired: about 0.66 s extra
compiler time for this edit. This is one local package and edit, not a general
build-speed estimate. Retention ages were simulated; the run does not measure
long-term cache usage. It demonstrates that reclaiming old configuration caches
preserves fresh artifacts, while revisiting an evicted configuration costs more
on its next source edit.

The [first-prototype receipt](results/macos-aarch64.json) is retained as historical
evidence from before the correctness and tracking-overhead fixes. The current
measurements above supersede it for this implementation.

## Measure tracking overhead separately

Expiry makes the next edit to an evicted configuration slower. Tracking can also
add work to an otherwise fresh build, so measure it independently with one pinned
Cargo executable. Prefer a release build with `--features ohm-defaults`; the
`--cargo-build-profile` argument records how that executable was built and does
not compile it. Run this while no other compilation or benchmark is active:

```sh
python3 benches/incremental-gc/tracking_perf.py \
  --cargo /absolute/path/to/release/cargo \
  --cargo-build-profile release \
  --source /absolute/path/to/fixed/ruff-source \
  --output /private/tmp/codex-cargo-targets/cargo/isolated/incremental-gc/tracking-release
```

The source must be an existing fixed Ruff snapshot with `Cargo.lock`, and its
registry dependencies must already be available in the shared Cargo home. The
harness does not edit that source. It creates a second workspace containing 100
tiny local dependencies and a root crate, making per-unit bookkeeping visible
without introducing registry or compilation work into the measured samples.

Both modes explicitly enable fine-grained locking and shared registry caching.
Mode A omits `-Zohm-incremental-gc`; mode B enables it. They use the same Cargo
executable, Ohm compiler, source, flags, and new shared-build root, with separate
fixed target namespaces. Do not alternate the flag in a single namespace: output
warmed with tracking disabled can already be fresh when tracking is enabled,
without having created a managed incremental payload. Separate namespaces let
each mode populate its own caches before timing.

After warming both modes until all compiler artifacts are fresh, the harness
runs 32 no-op builds per workload in repeated ABBA/BAAB order. Every measured
artifact must remain fresh. It records wall times, all per-run commands and Cargo
JSON output, executable and source hashes, paired four-run block differences,
and an approximate confidence interval to show local timing noise. Its eight
serial block measurements are not independent machines or workloads; a small
percentage within that noise is not evidence of a performance improvement.

Ownership-marker snapshots compare content, modification time, and inode before
and after each workload. They show whether the fresh invocations rewrote markers;
they do not count every filesystem syscall. The result also verifies that the
source snapshots and Cargo/rustc executables did not change. All output remains
under the bounded experiment directory as durable evidence.

Current version-2 ownership records keep the actual refresh time in `last_used`.
Fresh invocations within one hour validate existing records without rewriting
them. Collection adds that one-hour interval to the recorded time before testing
expiry, so a recent use omitted by throttling cannot cause premature eviction.
This can retain a cache for up to one extra hour, including with `--max-age '0 seconds'`.
Version-1 records remain readable and use their original expiry semantics; a new
use upgrades them to version 2.

### Current release tracking result: macOS arm64

The [release tracking receipt](results/tracking-release-macos-aarch64.json) records
32 fresh builds per workload on September 3, 2026, with the fixed Cargo executable
SHA-256 `f6e6e80c52b6b6ddedc44696ee333ae2a2113bea4201e325168bc33c896257bb`
and Ohm 1.98.0-8. Both modes used that same release executable.

| Fresh-build workload | Tracked local units | Disabled mean | Enabled mean | Difference |
| --- | ---: | ---: | ---: | ---: |
| Ruff parser, 97 artifacts | 5 | 79.48 ms | 78.42 ms | -1.06 ms (-1.3%) |
| Synthetic, 101 artifacts | 101 | 47.58 ms | 49.23 ms | +1.65 ms (+3.5%) |

The approximate paired-block intervals were -3.31 to +1.19 ms for Ruff and
-0.25 to +3.56 ms for the synthetic graph. Both include zero: this run does not
establish a speedup, zero overhead, or a precise slowdown percentage. Every
measured artifact was fresh, and none of the 106 ownership markers changed in
content, modification time, or inode. The repeated writes within the refresh
interval are gone. Validation still reads markers and adds bookkeeping.

This compares enabled and disabled tracking within one executable. It does not
measure the speed difference between Cargo revisions or build profiles.
