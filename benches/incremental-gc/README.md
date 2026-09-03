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

## Recorded result: macOS arm64

The September 3, 2026 run used Ruff revision
`0a5ec91697d9d3267392b471580c67e694b9e318` and Ohm 1.98.0-8. The
[checked-in receipt](results/macos-aarch64.json) preserves executable and source
hashes, per-unit payload digests, cleanup output, exact measured compiler arguments,
artifact freshness and all eight timing samples.

Three debug configurations produced 15 caches across five workspace crates. After
simulating 40 days of inactivity and refreshing debug=2, the 30-day collection
removed the ten caches belonging to debug=0 and debug=1:

| Managed incremental state | Before | After |
| --- | ---: | ---: |
| Configuration caches | 15 | 5 |
| Files | 786 | 262 |
| Logical size | 349.43 MiB | 128.05 MiB |
| Allocated size, deduplicated by inode | 353.44 MiB | 129.46 MiB |

The reduction was **221.38 MiB of logical data, or 63.4%**. Allocation estimates
fell by 223.98 MiB; these are not physical free-space measurements and do not
account for shared APFS extents. The dry run changed no snapshot fields. All five
retained caches were unchanged. Both configurations tested immediately after
collection (debug=2 and debug=0) reported all 97 artifacts fresh and performed no
compilation.

Each measured next edit compiled only `ruff_python_parser`, with 96 other artifacts
fresh. The expired configuration took longer in both counterbalanced blocks:

| Sample order (A = retained, B = expired) | Retained median rustc time | Expired median rustc time |
| --- | ---: | ---: |
| ABBA | 0.469 s | 2.146 s |
| BAAB | 0.239 s | 0.920 s |

Timings were substantially lower in the second block, so the pooled ratio is not
a stable performance estimate. This run demonstrates the intended tradeoff: reclaiming old
configuration caches preserves fresh builds, while revisiting one costs more on
its next source edit. Retention ages were simulated; this is one local workload,
not a measurement of long-term cache usage.
