# Whole-Cargo wall time after editing an inactive Ruff profile

On this Linux x86-64 host, retaining the workspace resolution after a real edit to Ruff’s trailing `[profile.fast-test]` section reduced the median edited package build from **190.03 ms to 62.81 ms**. The paired reduction was **66.49%**, with a 95% interval of **66.32% to 66.84%**. The candidate finished sooner in all 32 primary pairs. On the separate serde integration selection, it also finished sooner in all 32 edited pairs. Neither unchanged-repeat interval excludes zero.

| Cargo visit | Parent median | Candidate median | Median paired saving | Paired reduction [95% interval] | Candidate faster | Two-sided sign p |
|---|---:|---:|---:|---:|---:|---:|
| Package build after edit | 190.03 ms | 62.81 ms | 126.49 ms | 66.49% [66.32%, 66.84%] | 32/32 | 4.66 × 10⁻¹⁰ |
| Package build, first unchanged | 61.85 ms | 61.55 ms | 0.02 ms | 0.04% [−2.83%, 1.74%] | 17/32 | .860 |
| Package edit + first unchanged | 252.95 ms | 124.59 ms | 127.75 ms | 49.96% [49.13%, 50.88%] | 32/32 | 4.66 × 10⁻¹⁰ |
| Serde test build after edit | 202.54 ms | 72.83 ms | 130.64 ms | 63.26% [62.63%, 65.65%] | 32/32 | 4.66 × 10⁻¹⁰ |
| Serde test build, first unchanged | 73.84 ms | 72.80 ms | 0.70 ms | 1.01% [−1.46%, 6.75%] | 19/32 | .377 |
| Serde edit + first unchanged | 274.98 ms | 146.48 ms | 128.61 ms | 46.97% [45.07%, 50.18%] | 32/32 | 4.66 × 10⁻¹⁰ |

Ruff `93526150df078af7dd8fc4226cdcc469539d2001` supplied the real package, integration test, workspace root, and unchanged 138,994-byte, 553-package Cargo.lock. Reversing and restoring the three lines from `6dc1031889aa24a0461457409d39861e279242a9` changed only the inactive fast-test profile. The complete manifest has two identical three-line strings. The runner selects the unique occurrence under the authenticated profile header. The build probe used `cargo +ohm build -p ruff_text_size --locked --offline`. The integration probe used `cargo +ohm test -p ruff_text_size --features serde --test serde --no-run --locked --offline`. These are settled builds with the Rust artifacts already present. [Ruff source](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [historical edit](https://github.com/astral-sh/ruff/commit/6dc1031889aa24a0461457409d39861e279242a9)

All 256 scored Cargo invocations used ordinary text output without tracing, profiling or resolver logging. A common parent supplied byte-validated warm output for both writable snapshots at the same logical path. Four logical CPUs ran the matched private release-profile PGO Cargo images. The parent was `2fe90823d8eadc95de56c2cde8d41e0082aac0eb`. The candidate was `97e5acfb7b8eefde1ce07d703fc4849d6d36e37c`. The comparison binds both executable hashes and their common display version. The candidate’s immediate Git parent differs from the measured parent only in a test file. The compiler profile, 239 independent externs and 335 native link inputs in the Cargo builds matched. The measured commands used the same enrolled rustc `5694abe5…` and stock Wild `0d633580…`. [Subjects and input receipts](subjects.json)

There were 32 chronological paired visits for each selection. Pair order repeated AB/BA/BA/AB, balanced within each of the two edit directions. Each paired visit included an edited command and its immediate unchanged repeat on both arms. Source preparation, trace controls and caller checks ran outside the clocks. The interval is a 20,000-draw paired bootstrap for the median per-pair percent reduction, stratified by edit direction and arm order. The frozen primary criterion was an edited interval excluding zero and a two-sided sign-test p below .05. The primary reduction was 66.68% on reversal and 66.33% on restoration. The corresponding serde medians were 64.91% and 62.93%. All order groups, extremes and unfavorable repeat pairs are preserved. [Prospective design](design.md) · [directions and extrema](directions.json) · [full precision statistics](reported-statistics.json)

## Products and native launches

The package unit produced two declared files. Every on-host control had the same complete rlib `bf871a85…` and rmeta `af8f228d…`. A separate real Rust consumer linked the declared library, returned exactly `17 29 12`, and had the same entire executable SHA-256 `9fd6acb5896e86a2c59526eb0b1c63aa1b5cdd02f8fd0f50e9f7012540a2e53d`. The serde plan contained 19 units, 15 compiler-artifact messages and four build-script-executed messages, with 24 declared files. All complete bytes matched the common seed on every control of both arms. The actual integration executable SHA was `3806e14ac4f4fb8745b6d4bd90e98a08d287b01942ee26ee2e1fd87bc22efe1c`. The harness listed and passed `invalid_range_deserialization`, `range_serialization` and `size_serialization`.

The stock common package warm-up invoked one source rustc plus two probes. The common serde warm-up invoked 15 source rustcs, eight probes, four build scripts, six instances each of cc and collect2, and six stock Wild links. The source controller’s original single-line counter saw only ten source compiles and five links on serde because nine successful execs crossed trace lines. The packet retains its original counts and a second parser joining every unfinished/resumed syscall by PID. The other 22 off-clock invocations each consisted of the genuine rustup proxy and target Cargo executable, with zero native compiles or links, all typed artifacts fresh. Those counts come from the surrounding off-clock invocations. Each scored row separately retains the actual exit, whole-command elapsed nanoseconds, empty stdout, and ordinary Cargo stderr.

A second independent run, after the wall cohorts closed, enabled Cargo resolver debug logging for these exact selections. All eight genuine edited control commands each ran one full workspace resolution. Each candidate edit ran zero full resolutions and one cached lookup. Neither arm ran a source compiler or linker on any of these edits or unchanged repeats. All six native links from the separate serde warm-up and all additional observations are retained apart from the timings. There were 40 commands. Each newly warmed graph had identical complete files across arms throughout that graph. Between the independent wall and logging warm-ups, the only changed file in each selection was the complete `ruff_text_size.rlib`. The rmeta, package caller, and complete serde executable remained byte-identical. The data does not isolate which archive bytes differ. [Logging protocol](mechanism-design.md) · [all four raw archive hashes](mechanism-results.json)

Two further correctness packets exercise real rebuilds and failure paths with these Cargo images. The synthetic case captures profile validation, true dependency edits and a raw-manifest build script. The active Ruff case uses a different historical change to the default development profile and released -18 Rust. It records the genuine changed program, matching empty build, three tests and the full warm/clean compiler errors. [Synthetic controls](../rc20-profile-workspace-resolve-safety/) · [active Ruff edit](../rc20-profile-workspace-resolve-ruff-active/)

## Verify or rerun

From this directory with Python 3.11 or later:

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
python3 -IB mechanism.py
python3 -IB check_replay.py
```

`wall-native.json.gz` contains all 256 original clock counts and exact chronological order, 24 full native/typed output streams, the source worker’s own coarse jobs ledger, complete argv hashes for all successful native launches, declared file hashes, real callers, both terminal rosters and six enrollment records. `raw-file-index.json.gz` records all 885 original files, each verified against the native tar before export. Across the scored roster every stdout is empty, every elapsed count is a positive integer, and every exit is zero on the scored roster. Text streams and non-scored kernel exec traces replace private filesystem roots, account names, and the registry cache bucket with role labels. Literal raw file SHA-256s remain available. `native-mechanism.json.gz` contains the separate 40-command raw-hash/stream/event projection. Ten mutations challenge the clocks, order, ordinary stderr, missing output, runtime identity, unwanted process, deleted paired observation, missing native trace, feature roster, and a forged resolver event. The verifier rejects each. These programs read the packet without a Rust toolchain.

For another native Linux x86-64 run, use a non-root account with rustup proxies, Git, strace, util-linux, GNU coreutils, an offline Cargo registry/Git cache for Ruff, and permission to create private mount namespaces using `sudo -n unshare --mount`. The two release-profile Cargo files and an SDK matching the actual enrolled rustc and Wild must be supplied. The scratch directory must be absent and the file system must support OverlayFS. Supply 24 GiB or more free reserve for HOME and scratch, plus space for the new read-only lower. Both original cohorts additionally retained 16 GiB of tmpfs free. The portable runner clones the pinned source, prepares one common warm seed, uses isolated same-path writable arm views and drops capabilities before calling Cargo. The full timing work is intentionally omitted from this packet’s author-side reruns. The source and schedule check, controller protocol, matched/wrong-input gates and the clock body’s exact syntax tree were independently verified.

```sh
python3 -IB replay.py --checkout "$RUFF" --check-source
python3 -IB replay.py --scratch "$NEW_RUN" --checkout "$RUFF" \
  --cargo-a "$PARENT" --cargo-b "$CANDIDATE" --sdk "$SDK" \
  --cargo-home "$OFFLINE_CARGO_HOME" --rustup-proxies "$RUSTUP_PROXIES" --cpus 0,1,2,3
python3 -IB analyze.py "$NEW_RUN/results" build test

# Optional native mechanism only, with a different absent destination.
python3 -IB replay.py --mechanism-only --scratch "$NEW_LOG_RUN" --checkout "$RUFF" \
  --cargo-a "$PARENT" --cargo-b "$CANDIDATE" --sdk "$SDK" \
  --cargo-home "$OFFLINE_CARGO_HOME" --rustup-proxies "$RUSTUP_PROXIES" --cpus 0,1,2,3
```

The flat `timings.csv` lists every original nanosecond count, source, order, arm, phase, exit and native output digest in chronological order per workload. The verifier reconstructs every CSV row from the original per-arm clock files.

The source capture is bound to the accompanying Ruff license. Cargo-side materials are available under the included MIT and Apache-2.0 licenses. Each fresh installation must use its own observed product hashes. Different absolute paths or independently compiled intermediates can change them.
