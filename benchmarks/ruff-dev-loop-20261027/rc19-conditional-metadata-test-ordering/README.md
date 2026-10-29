# Conditional metadata test marker ordering

## Fresh Linux reproduction

The packet includes the wrapper extracted from the pinned Cargo test. Its exact SHA-256 and the fixed wrapper's digest are checked before compilation. A reviewer can run both histories from this directory with Python 3.9+, Rustup, a C compiler, GNU patch, and strace. Install stock Rust 1.99.0 and select a released Ohm Cargo as the Rustup toolchain named `ohm`. The public-release replay used Ohm 1.99.0-6. [Published Ohm release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-6) · [Pinned test source](https://github.com/astral-sh/ohm-cargo/blob/242e7bdc885910beff6872f71300968933293410/tests/testsuite/freshness.rs#L3418)

```sh
sha256sum -c SHA256SUMS
python3 -IB reproduce.py --trace --work "$(mktemp -d)/replay"
```

The driver compiles the two small wrappers and two dependency-free local crates into fresh private targets. It enforces the three-second notification gate, Cargo exit statuses, marker ordering, recovery of the dependency fingerprint and both compiler invocations, followed by a fully fresh build. With `--trace`, it also decodes the kernel traces and checks the actual compiler launches, the consumer's stat, and the producer's failure. Each run retains stdout, stderr, observations, and traces under the supplied new directory. Omit `--trace` where ptrace is unavailable to run the same bounded behavior checks.

Expected terminal output:

```text
original: failure=101, early-marker=False, recovery=['app', 'dep'], unchanged=[]
proposed: failure=101, early-marker=True, recovery=['app', 'dep'], unchanged=[]
```

The optional `--checkout /path/to/ohm-cargo` independently extracts and compares Git blob `b5669ba429e093d9b23c480151cde0162ba178ba` from commit `242e7bdc885910beff6872f71300968933293410`. The local checkout can be on another branch if it contains that commit. `--cargo` and `--rustc` accept physical toolchain executables for testing a different compatible pair. The study added the same post-flush handshake to each wrapper, and changed the marker writes only in the proposed version. The bundled source is distributed under the original Cargo licenses. [MIT license](https://github.com/astral-sh/ohm-cargo/blob/242e7bdc885910beff6872f71300968933293410/LICENSE-MIT) · [Apache 2.0 license](https://github.com/astral-sh/ohm-cargo/blob/242e7bdc885910beff6872f71300968933293410/LICENSE-APACHE)

`fresh-reruns.json` records two independent end-to-end executions of this driver. All 16 Cargo commands passed, eight with the published release and eight with the pinned release-PGO review Cargo. Both used the CI version of stable rustc. The syscall evidence and prior 48-command packet are independently bound below.

## Earlier CI investigation

Linux CI at commit 9d675d9393 failed the assertion that the early parent marker existed. The CI log shows the failed assertion and supplies no syscall ordering. A real two-crate replay on the same stable Rust 1.99.0 commit demonstrates a sufficient cause. The producer forwards its metadata, Cargo schedules the dependent, the dependent checks for the producer marker and observes ENOENT, and the producer then creates it. The proposed fixture writes its marker before forwarding the notification. The dependent sees it and records its early start. [Linux CI job](https://github.com/astral-sh/ohm-cargo/actions/runs/40861803322/job/123406651757)

The helper and the failing test first appeared in 61294b1c on the closed #27. Their rewritten commit 242e7bdc on #71 is an ancestor of #284. The sole difference between the #71 and #284 wrapper bodies is the additional filtered compiler argument shown in 71-to-284.diff. The 293 branch heads in the accompanying GitHub snapshot include 231 with this helper and both markers after the notification, 49 with the test file but no helper and 13 without the test file. [Original proposal](https://github.com/astral-sh/ohm-cargo/pull/27) · [Rewritten implementation](https://github.com/astral-sh/ohm-cargo/pull/71/commits/242e7bdc885910beff6872f71300968933293410)

Both fixture versions received the same private hook immediately after stderr flush. It waits on an inotify watch for the dependent's existing nonempty start marker. That marker is created after the dependent has checked the producer. The three-second deadline never fired. The actual rustc first emitted a metadata artifact. The fixture added its synthetic public API hash and performed its original intentional producer failure. The fixed and original schedules both returned Cargo 101, removed the uncommitted hash, rebuilt both crates on recovery, and launched zero fixture compilers on the following build. Exact-compiler comparisons used the real Linux CI stable rustc 1.99.0 (b940084d7) with a prequalified release-PGO Cargo at 8dc33c9cc. The private release Cargo required its automatic Ohm defaults disabled to match the CI test-profile Cargo with stable rustc. Each used the checked-in wrapper and its explicit public-API flag.

The first 40 commands include the original and proposed versions for #71 and #284 on stable 1.98.1, a two-crate middle-to-app control showing the same missing-marker effect, and the original three-crate unchanged-middle and binary barriers. During either three-crate edit the middle compiler started before the dependency finished, and the app waited for middle to finish. The corrected marker records both observations. The final eight commands repeat the decisive #284 failure, recovery and unchanged build on the CI compiler.

The full syscall files, process streams, fixture executables and original failed preflights remain in the private raw directory. The two checked-kernel-order JSON files bind every kernel trace, process stream and phase report, and retain the actual line numbers of the decisive syscalls. With the private raw directory available, rerun the independent extraction and the source comparisons with:

```sh
python3 -IB verify-native.py "$RAW" --output /tmp/metadata-order-stable98.json
cmp checked-kernel-order.json /tmp/metadata-order-stable98.json
python3 -IB verify-native.py "$RAW/ci-stable-1.99" --cases 2 --output /tmp/metadata-order-stable99.json
cmp checked-ci-kernel-order.json /tmp/metadata-order-stable99.json
sha256sum -c SHA256SUMS
```
