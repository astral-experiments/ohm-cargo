# Ruff lockfile serialization and whole-Cargo wall time

Retaining the lockfile writer’s canonical encoding did not establish a whole-command speedup on either Ruff workload. Each row uses 32 adjacent pairs of matched release-profile PGO Cargo processes. Positive numbers mean the candidate finished sooner. The interval is the stratified 95% paired bootstrap interval for the median percentage reduction.

| Command and phase | Median paired reduction | 95% interval | Median paired time saved | Candidate faster | Two-sided sign test |
| --- | ---: | ---: | ---: | ---: | ---: |
| Package build, manifest edit | −0.63% | [−12.57%, +1.78%] | −1.24 ms | 15/32 | 0.860 |
| Package build, first unchanged | −2.37% | [−5.03%, +1.59%] | −1.60 ms | 14/32 | 0.597 |
| Package build, edit + first unchanged | −1.02% | [−9.07%, +1.15%] | −2.77 ms | 14/32 | 0.597 |
| Serde integration build, manifest edit | −0.84% | [−4.45%, +1.06%] | −1.61 ms | 14/32 | 0.597 |
| Serde integration build, first unchanged | +0.45% | [−3.79%, +2.25%] | +0.32 ms | 18/32 | 0.597 |
| Serde integration build, edit + first unchanged | −0.28% | [−2.77%, +1.29%] | −0.74 ms | 15/32 | 0.860 |

Reversing the hunk on the primary build had a median **14.36% slowdown** across 16 edit commands, while restoring it had a median **1.46% reduction**. The most adverse edit was pair 20, parent first, with 177,755,623 ns for the parent and 587,817,481 ns for the candidate. Its first unchanged commands were also retained. The candidate took 719,868,932 ns for that complete loop versus 238,927,939 ns for the parent. The aggregate includes every pair. The direction breakdown describes the observation. No cause for the slow pair was established. [Both directions, both orders and extrema](directions.json).

The primary selection was `cargo +ohm build -p ruff_text_size --locked --offline`. The second was `cargo +ohm test -p ruff_text_size --features serde --test serde --no-run --locked --offline`. Each edit reversed or restored the historical three-line change under `[profile.fast-test]`. Both commands use other profiles. The lockfile stayed byte-identical at 138,994 bytes and 553 packages. The experiment measures default Cargo overhead when both selections are already built. [Ruff revision](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [Historical manifest change](https://github.com/astral-sh/ruff/commit/6dc1031889aa24a0461457409d39861e279242a9).

The private Cargo images carry the same build-version stamp. Their exact SHA-256s are in `subjects.json`. The candidate keeps the final encoding returned by the lockfile writer. At cache publication it reads and shared-locks the current file, compares its lines, and runs the original serializer if those lines differ. Its immediate Git parent differed from the measured parent only in Cargo tests. Both binaries used the same PGO profile, Rust compiler commands, 239 external compiler inputs and 335 durable native link inputs. [Measured parent](https://github.com/astral-sh/ohm-cargo/tree/2fe90823d8eadc95de56c2cde8d41e0082aac0eb) · [Candidate source](https://github.com/astral-sh/ohm-cargo/tree/24c98100d04843e60a830951f843ab40f6e60414).

The separate mechanism study counted one serialization on each manifest transition in the candidate and two in the parent. Both still read the full lockfile four times. In that 33-command study, an external writer changed comments, package versions or syntax between independently released locks. There were 27 successful unchanged caller ELFs and six expected errors. Those commands have their own raw inputs, verifier and four rejected packet mutations. They are outside the 256 clocks. [Writer and error controls](https://github.com/astral-sh/ohm-cargo/tree/722ba625259aa8589954b77ae3fdffce29dc6f7d/benchmarks/ruff-dev-loop-20261027/rc20-workspace-lockfile-serialization-candidate).

## Clocks and native controls

Each workload used a common warm-up with the parent Cargo. Independent writable overlays then exposed the same warm source, registry, target and shared files at the same absolute paths. The ordinary user ran on Linux x86-64, CPUs 0–3. The four-pair order was AB, BA, BA, AB, repeated eight times. Each pair timed an edit immediately followed by its first unchanged command on each arm. Source placement, admission, tracing, artifact hashing and execution of external callers were outside the measured interval. The timer covered the rustup Cargo invocation through subprocess completion. For each comparison the original analysis took the median of `100 × (parent − candidate) / parent`, resampled the four equal edit-direction/order strata 20,000 times, and tested the non-tied signs. All 256 enrolled processes exited 0. No failed or substitute slot entered these estimates. [Frozen design](design.md) · [Full estimates and direction medians](reported-statistics.json).

The one-unit warm-up ran one source compiler. Every subsequent traced package build returned the same complete rlib (`9afcd7b81653b5d7c7cfa11d5612737f763e71fb80cb0ae923e4b893910c46d1`) and standalone rmeta (`af8f228d9e5e76c736b54649f65b2d4089f01edc16ee615df49142e8f373f9a9`). A separately compiled consumer loaded the real rlib and printed `17 29 12` every time. The 19-unit serde graph produced 15 compiler artifacts, four build-script execution records and 24 declared files. Both arms returned the same complete executable (`3806e14ac4f4fb8745b6d4bd90e98a08d287b01942ee26ee2e1fd87bc22efe1c`). All three checked-in tests passed, including invalid range deserialization.

Reparsing the raw chronological strace records corrected the original warm-up census. Its line-only expression recognized 12 source compilers and five cc processes in the serde warm-up and missed four successful execs split across two lines. Joining unfinished and resumed calls by PID found **15 source rustc, eight rustc probes, four build-script processes, six cc, six collect2 and six stock Wild links** in the common serde warm-up, along with the two Cargo execs. The package warm-up had one source rustc, two rustc probes and two Cargo execs. Each of the other 22 traced guards had only the Cargo proxy and the selected Cargo. The two original warm-up summaries and the corrected process rows are both preserved. Timed commands ran with ordinary text output and no tracer. Their streams and the surrounding native controls provide different kinds of evidence. [Complete process parser](native_execs.py).

The sole serialization wall cohort completed on the first attempt. It used the registered common warm donor and retained the full output comparisons. Its independent whole-kernel-exec ledger agrees with the completed-call parser for all 24 captures. The previous decoding study’s two failed preparations belong to a different product and are excluded from this cohort.

The separate local lockfile compatibility check made 66 real Cargo metadata calls. The legacy v1, v2, v3, v4 and unused-patch cases succeeded throughout. Five malformed or inconsistent inputs failed all three calls on each arm. A mixed-format file failed under `--locked`, rewrote on the ordinary call, and succeeded on the next locked call. Both arms produced identical normalized stdout, stderr and complete lockfile at all 33 comparison points. [Compatibility inputs and outcomes](legacy.json.gz).

## Verify the recorded study

From this directory with Python 3.11 or newer, run

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
```

With the published writer-control folder alongside this packet, `python3 -IB verify.py --self-test --writers ../rc20-workspace-lockfile-serialization-candidate` also authenticates every file in that receipt and reruns its 33 commands’ recorded assertions and four negative checks offline.

`wall-native.json.gz` contains both historical terminal ledgers, every individual timer row and its original hash, all ordinary stdout and stderr with their hashes, and the complete typed JSON messages for all 24 native controls. Successful kernel execs have their raw line numbers, argv hash, program, relevant source/output fields and Cargo arguments. Raw trace and stream hashes bind the projection to the source. Only private machine paths, source-cache bucket names and account fields are replaced in the public representation. The reported package stderr is byte-exact. The serde stderr replaces the absolute arena prefix in its executable path. The compatibility fixture replaced its own absolute root with `<fixture>` before comparing arms. The full root Cargo.toml, lockfile, historical patch and upstream license are included. `project.py` reproduces the projection for anyone holding the original archives.

The independent verifier recomputes every statistic and checks the structural gates. Its mutation cases change a timer, the chronological roster, an ordinary stream, an artifact, a consumer verdict, a worker launch and a legacy failure. An eighth case removes the most adverse primary edit and recomputes its terminal hash. The checks use only the contents of this packet. 

## Replay native timing on another Linux x86-64 system

Use a non-root account with Python 3.11+, Git, rustup proxies, strace, GNU coreutils, util-linux and working `sudo -n unshare --mount` with OverlayFS. Supply the two enrolled private release-profile PGO Cargo executables, their compatible Ohm runtime and an offline Cargo registry/Git cache for the pinned workspace. `replay.py` verifies the original executable, rustc, Wild, lockfile, historical edit and source digests before launching a measurement. It accepts only a new scratch root. Privileged operations are limited to its private mount namespace and drop all capabilities before running the worker. Choose an executable, native OverlayFS backing filesystem. The worker requires four available CPUs and at least 24 GiB free in both HOME and scratch. The replay keeps its frozen common warm-up, both arms, raw streams, stop records and results locally. Supplying a private registry configuration is optional and must be limited to a credentials-free offline source mapping.

```sh
# Set these to existing local inputs. ABSENT must name a new directory.
RUFF=/path/to/ruff
ABSENT=/path/to/new-run
PARENT=/path/to/parent/cargo
CANDIDATE=/path/to/candidate/cargo
SDK=/path/to/ohm-toolchain
OFFLINE=/path/to/offline-cargo-home

python3 -IB replay.py --checkout "$RUFF" --check-source
python3 -IB replay.py --scratch "$ABSENT" --checkout "$RUFF" \
  --cargo-a "$PARENT" --cargo-b "$CANDIDATE" --sdk "$SDK" \
  --cargo-home "$OFFLINE" --rustup-proxies "$HOME/.cargo/bin" --cpus 0,1,2,3
python3 -IB analyze.py "$ABSENT/results" build test
```

The build-only or test-only variants accept `--workload build` or `--workload test`. The replay uses a single fresh filesystem for the common donor and private writable layers. The original trial kept the lower/overlay backing and measurement records on separately reserved storage and checked a 16 GiB tmpfs floor as well. Source enrollment, namespace command syntax, the controller's schedule and its unequal-product refusal, and identity of the clocked worker body were checked during packaging. The complete 256-command timing replay was not repeated. Runtime digests and declared output checks must pass within each new run. A different absolute path can change locally compiled output digests.

To reproduce the separate compatibility fixture on a system with its own 45 GiB free-space reserve, run

```sh
COMPAT_SDK=/path/to/compatibility-ohm-toolchain
python3 -IB legacy_replay.py --output /path/to/new-compatibility-run \
  --parent "$PARENT" --candidate "$CANDIDATE" --sdk "$COMPAT_SDK"
```

The recorded compatibility commands used the separately qualified common QA Rust SDK. Its compiler SHA-256 was `fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512`. The compatibility tool requires that compiler, matching Cargo images and equivalent A/B diagnostics and rewrites.
