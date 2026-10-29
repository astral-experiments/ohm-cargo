# Ruff lockfile decoding and whole-Cargo wall time

Reusing a typed lockfile after a resolve-cache miss did not establish a whole-command speedup on either Ruff workload. Each result below uses 32 adjacent pairs of matched release-profile PGO Cargo processes. Positive numbers mean the candidate finished sooner. The interval is the stratified 95% paired bootstrap interval for the median percentage reduction.

| Command and phase | Median paired reduction | 95% interval | Median paired time saved | Candidate faster | Two-sided sign test |
| --- | ---: | ---: | ---: | ---: | ---: |
| Package build, manifest edit | +0.45% | [−5.99%, +3.28%] | +0.81 ms | 17/32 | 0.860 |
| Package build, first unchanged | +1.90% | [−2.80%, +8.61%] | +1.15 ms | 19/32 | 0.377 |
| Package build, edit + first unchanged | +1.09% | [−6.62%, +4.83%] | +2.59 ms | 18/32 | 0.597 |
| Serde integration build, manifest edit | −1.38% | [−7.09%, +1.69%] | −2.75 ms | 13/32 | 0.377 |
| Serde integration build, first unchanged | −1.32% | [−7.12%, +1.17%] | −0.92 ms | 13/32 | 0.377 |
| Serde integration build, edit + first unchanged | −2.05% | [−5.62%, +1.22%] | −5.30 ms | 12/32 | 0.215 |

The primary selection was `cargo +ohm build -p ruff_text_size --locked --offline`. The second was `cargo +ohm test -p ruff_text_size --features serde --test serde --no-run --locked --offline`. Each edit reversed or restored the historical three-line change under `[profile.fast-test]`. Both commands use other profiles. The lockfile stayed byte-identical at 138,994 bytes and 553 packages. The experiment measures default Cargo overhead when both selections are already built. [Ruff revision](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [Historical manifest change](https://github.com/astral-sh/ruff/commit/6dc1031889aa24a0461457409d39861e279242a9).

The private Cargo images carry the same build-version stamp. Their exact SHA-256s are in `subjects.json`. The candidate retains the first owned typed lockfile and its source bytes across a cache miss. It still performs the ordinary second read, checks literal byte equality, and rebuilds the resolve graph. Its immediate Git parent differed from the measured parent only in Cargo tests. Candidate and measured parent used the same PGO inputs, Rust compiler command, 239 external compiler inputs and 335 native link inputs. [Measured parent](https://github.com/astral-sh/ohm-cargo/tree/2fe90823d8eadc95de56c2cde8d41e0082aac0eb) · [Candidate source](https://github.com/astral-sh/ohm-cargo/tree/0e398aa5aa13fa8b88b59c965d229923e53ab8cd) · [Independent lockfile reread and path-discovery controls](https://github.com/astral-sh/ohm-cargo/tree/693aed7d524e11be290b3319823085a6d0e0abac/benchmarks/ruff-dev-loop-20261027/rc20-lockfile-decode-reread-safety).

## Clocks and native controls

Each workload used a common warm-up with the parent Cargo. Independent writable overlays then exposed the same warm source, registry, target and shared files at the same absolute paths. The ordinary user ran on Linux x86-64, CPUs 0–3. The four-pair order was AB, BA, BA, AB, repeated eight times. Each pair timed an edit immediately followed by its first unchanged command on each arm. Source placement, admission, tracing, artifact hashing and execution of external callers were outside the measured interval. The timer covered the rustup Cargo invocation through subprocess completion. For each comparison the original analysis took the median of `100 × (parent − candidate) / parent`, resampled the four equal edit-direction/order strata 20,000 times, and tested the non-tied signs. All 256 enrolled processes exited 0. No failed or substitute slot entered these estimates. [Frozen design](design.md) · [Full estimates and direction medians](reported-statistics.json).

The one-unit warm-up ran one source compiler. Every subsequent traced package build returned the same complete rlib and standalone rmeta. A separately compiled consumer loaded the real rlib and printed `17 29 12` every time. The 19-unit serde graph produced 15 compiler artifacts, four build-script execution records and 24 declared files. Both arms returned the same complete executable and all three checked-in tests passed, including invalid range deserialization.

Reparsing the raw chronological strace records corrected the original warm-up census. Its line-only expression missed successful calls split across two lines. Joining unfinished and resumed calls by PID found **15 source rustc, eight rustc probes, four build-script processes, six cc, six collect2 and six stock Wild links** in the common serde warm-up, along with the two Cargo execs. The package warm-up had one source rustc, two rustc probes and two Cargo execs. Each of the other 22 traced guards had only the Cargo proxy and the selected Cargo. The two original warm-up summaries and the corrected process rows are both preserved. Timed commands ran with ordinary text output and no tracer. Their streams and the surrounding native controls provide different kinds of evidence. [Complete process parser](native_execs.py).

Two earlier attempts stopped before their first timed slot. The first rejected a repeated hunk outside the selected profile. The next found different whole rlib hashes in independently hydrated stores despite an identical rmeta, consumer ELF and runtime result. The scored run hydrated each workload once and checked the complete products after cloning the common donor. Both excluded archive identities and original tracebacks are preserved. [Excluded preparations](excluded.json).

The separate local lockfile compatibility check made 66 real Cargo metadata calls. The legacy v1, v2, v3, v4 and unused-patch cases succeeded throughout. Five malformed or inconsistent inputs failed all three calls on each arm. A mixed-format file failed under `--locked`, rewrote on the ordinary call, and succeeded on the next locked call. Both arms produced identical normalized stdout, stderr and complete lockfile at all 33 comparison points. [Compatibility inputs and outcomes](legacy.json.gz).

## Verify the recorded study

From this directory with Python 3.11 or newer, run

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
```

`wall-native.json.gz` contains both historical terminal ledgers, every individual timer row and its original hash, all ordinary stdout and stderr with their hashes, and the complete typed JSON messages for all 24 native controls. Successful kernel execs have their raw line numbers, argv hash, program, relevant source/output fields and Cargo arguments. Raw trace and stream hashes bind the projection to the source. Only private machine paths, source-cache bucket names and account fields are replaced in the public representation. The reported package stderr is byte-exact. The serde stderr replaces the absolute arena prefix in its executable path. The compatibility fixture replaced its own absolute root with `<fixture>` before comparing arms. The full root Cargo.toml, lockfile, historical patch and upstream license are included. `project.py` reproduces the projection for anyone holding the original archives.

The independent verifier recomputes every statistic and checks the structural gates. Its mutation cases change a timer, the chronological roster, an ordinary stream, an artifact, a consumer verdict, a worker launch and a legacy failure. The checks use only the contents of this packet. 

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
