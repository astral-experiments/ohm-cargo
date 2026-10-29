# Local replication of Ohm Cargo #286

Run two Cargo executables at one literal path against an installed Ohm SDK. The benchmark reverses and restores three lines of Ruff’s trailing `[profile.fast-test]` section. That profile is inactive in both selected commands. The package build has one planned unit. The optional serde integration selection has 19 planned units and executes its three tests outside the timed commands. The 553-package lockfile stays byte-identical. [Cargo change](https://github.com/astral-sh/ohm-cargo/pull/286) · [Ruff source](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [Ruff edit](https://github.com/astral-sh/ruff/commit/6dc1031889aa24a0461457409d39861e279242a9)

## Run from Git

Use a regular Linux x86-64 account, Python 3.12+, rustup proxies with a recent working Ohm toolchain, and its distributed Wild at `lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd`. The local example used the installed Ohm 1.99.0-18 runtime. Install Git, strace, util-linux, sudo, a native C toolchain, CMake, pkg-config, OpenSSL and zlib development files. Building the two Cargo products uses the system development libraries required by the pinned Cargo source and an Internet connection or a prehydrated Cargo cache. Allocate four available logical CPUs and use a quiet filesystem. The controller needs permission to run `sudo -n unshare --mount` and to mount OverlayFS inside its private namespace. It drops all effective capabilities and returns to the original account before running any Rust process. [Cargo source and build prerequisites](https://github.com/astral-sh/ohm-cargo/tree/97e5acfb7b8eefde1ce07d703fc4849d6d36e37c)

Keep the software clones, source-build outputs, and benchmarks in an ordinary trusted directory outside other Cargo workspaces. Allow 24–32 GiB in addition to your free-space reserve for two independent release builds and registry downloads. Actual usage depends on the SDK and build environment. The replay enforces at least 24 GiB free on HOME and scratch. Scratch also needs two copies of the supplied offline registry cache, the Ruff checkout and private build views. A small dedicated Cargo home avoids copying a large general-purpose cache. New output and scratch paths must be absent. Run the following from a new working directory with an installed `+ohm` toolchain.

```bash
set -euo pipefail
ROOT="$PWD"
git clone https://github.com/astral-sh/ohm-cargo.git ohm-cargo
git -C ohm-cargo fetch origin refs/pull/286/head
git -C ohm-cargo fetch origin \
  refs/heads/charlie/ohm-ruff-whole-skips-data-20261027:refs/remotes/origin/ohm-bench-evidence
git clone https://github.com/astral-sh/ruff.git ruff
git -C ruff switch --detach 93526150df078af7dd8fc4226cdcc469539d2001

mkdir evidence
PREFIX=benchmarks/ruff-dev-loop-20261027
git -C ohm-cargo archive origin/ohm-bench-evidence \
  "$PREFIX/rc20-profile-workspace-resolve-local-rerun" \
  "$PREFIX/rc20-profile-workspace-resolve-wall" | tar -x -C evidence
REPRO="$ROOT/evidence/$PREFIX/rc20-profile-workspace-resolve-local-rerun"
(cd "$REPRO" && sha256sum -c SHA256SUMS && python3 -IB verify.py)

SDK="$(rustc +ohm --print sysroot)"
CPUS="$(python3 -c 'import os; print(",".join(map(str,sorted(os.sched_getaffinity(0))[:4])))')"
mkdir offline-ruff
CARGO_HOME="$ROOT/offline-ruff" cargo +ohm fetch --locked --manifest-path "$ROOT/ruff/Cargo.toml"
python3 -IB "$REPRO/build_pair.py" --cargo-checkout "$ROOT/ohm-cargo" \
  --out "$ROOT/cargo-builds" --jobs 4
python3 -IB "$REPRO/run.py" --checkout "$ROOT/ruff" --sdk "$SDK" \
  --control "$ROOT/cargo-builds/A/cargo" --candidate "$ROOT/cargo-builds/B/cargo" \
  --pair-receipt "$ROOT/cargo-builds/build-receipt.json" \
  --cargo-home "$ROOT/offline-ruff" --cpus "$CPUS" --workload build \
  --scratch "$ROOT/benchmark-scratch" --out "$ROOT/benchmark-output"
python3 -IB "$REPRO/report.py" "$ROOT/benchmark-output" > "$ROOT/local-report.json"
cat "$ROOT/benchmark-output/wall/paired-wall.json"
```

For the 19-unit serde test, use `--workload test` and two new output/scratch paths. Use `both` to run both selections with separate common warmups and 32 pairs per selection. If using a registry mirror, pass the matching credentials-free `--registry-config`. The timed commands always use `--locked --offline`. The ordinary package command is `cargo +ohm build -p ruff_text_size --locked --offline`.

`build_pair.py` authenticates each source file against Git, including executable modes and literal symlink targets, and builds A `2fe90823d` and B `97e5acfb7` at one canonical source/target/shared path using the same SDK, flags, feature set and lockfile. Its fresh release-profile sources contain a shared three-line `git-commit-info`, using Cargo’s own source-tarball version mechanism. It finishes only when the two product digests differ and their complete `cargo -Vv` outputs match. It retains both release build logs. This public build route uses standard release flags. The original production comparisons used their private training profile. `--prepare-only` verifies and exports both trees without compiling. The candidate’s direct Git parent differs from the selected parent only in a test file. [Parent](https://github.com/astral-sh/ohm-cargo/commit/2fe90823d8eadc95de56c2cde8d41e0082aac0eb) · [candidate](https://github.com/astral-sh/ohm-cargo/commit/97e5acfb7b8eefde1ce07d703fc4849d6d36e37c) · [version reader](https://github.com/astral-sh/ohm-cargo/blob/97e5acfb7b8eefde1ce07d703fc4849d6d36e37c/build.rs)

For your own previously built pair, substitute its two files and matching source receipt. Without a receipt, supplied binaries are identified by their observed SHA-256 and equal full version; the runner cannot establish the source of an opaque executable. Every run enrolls the local rustc, driver and Wild. The measured artifact digests in this component are evidence of that run and are not requirements for another machine.

## Health and output

The adapter checks the sibling public template’s manifest and all six input files. It enrolls the current Cargo digests and local SDK in a fresh runner, points non-Cargo compiler tools at the actual installed files, and records their physical identities in each namespace. It keeps the original workload, source checks, clock body, order, analysis and native/behavioral gates. The separate logged qualification must pass before the timing controller runs. The common warmup compiles real Rust. Both A/B views must then show the same literal file paths and full product bytes, and every typed non-warm native control requires zero rustc compiles and zero links. A separately compiled consumer prints `17 29 12` in the one-unit workload. The untraced, unlogged timed processes each save raw stdout, stderr, exit status and monotonic elapsed nanoseconds. The root output directory retains the complete raw streams, resolver diagnostics and syscall exec traces, along with the adapted runner. `report.py` independently decodes the traces, checks Cargo arguments and actual compiler/link work, rejoins outputs, compares device/inode/timestamps for sdk tools and recomputes wall statistics. Its JSON report omits private filesystem prefixes.

Each workload runs 32 pairs, with AB/BA/BA/AB order balanced over both edit directions. Each arm gets the edit and its first unchanged repeat. The interval uses 20,000 stratified, paired bootstrap draws of median per-pair reduction. The sign-test P is two-sided. The editing, tracing, product hashing and caller execution are outside the measured command. [Immutable H8 results and protocol](../rc20-profile-workspace-resolve-wall/README.md)

## Executed local example

This independent example completed the entire one-unit selection with the supplied matched release-profile PGO binaries and the public -18 runtime. It used neither the original H8 machine nor its Rust image. The two public source exports were separately exercised and 3,108 Git objects and modes verified per source; no native rebuild of the Cargo products was part of this timed example. The serde timing series belongs to the sibling H8 packet.

| Local result | Parent median | Candidate median | Median paired reduction | 95% interval | Faster pairs |
|---|---:|---:|---:|---:|---:|
| Edited package build | 184.62 ms | 64.73 ms | 64.93% | 64.59% to 65.22% | 32/32 |
| First unchanged repeat | 65.01 ms | 64.12 ms | −0.02% | −0.25% to 1.86% | 15/32 |
| Edit plus repeat | 248.99 ms | 129.52 ms | 48.10% | 47.64% to 48.69% | 32/32 |

The separate logging run recorded one full resolution on the first candidate setup, then four candidate hits on real edits. The parent performed four full resolutions on those edits. The 128 timed launches and 32 separate native controls passed. Each independently seeded logging/timing namespace had a different absolute path, archive and compiled caller hash. Within each namespace the rlib, rmeta and entire caller ELF matched in both arms at all native visits. The expected external output was identical in both namespaces. [Exact nanoseconds, process streams, native counts, caller and file hashes](local-result.json) · [checked source exports](source-exports.json)

The initial physical space gate stopped before any command. Privilege-drop setup then stopped before a Cargo workload when the outer shell left an inaccessible HOME. The first genuine native attempt on copied SDK executables compiled one unexpected unit on the candidate, and emitted a different compiler-namespace directory. It was excluded with zero timed samples. Reusing the actual installed tool inodes made the next complete run pass every original output/argv gate. The original template and original H8 data remain byte-identical. The source-export preflight also caught a standard tar extractor dropping a trailing slash from a Git symlink target; the supplied Git blob reader preserves it. Two further real input-control invocations rejected equal arm binaries and swapped source receipts. [Native enrollment refusals](input-refusals.json)

The public verifier recomputes all statistics from the exact example clocks and exercises seven corruptions of clock count, arm order, stdout, caller, native work, resolver mechanism and effect. Run `python3 -IB verify.py` from this directory. The Bash replay above records separate results on the reviewer’s computer.
