# Ruff build and test-build under the complete Ohm stack

The comparison uses release 14’s PGO Cargo, the matched base PGO/BOLT rustc driver and its shipped Wild linker as control. The candidate combines the nine Cargo drafts, three rustc drafts and the paired-range Wild release package. The private-trait change only applies to check metadata. Each run recompiled and linked the one changed Ruff target against the same prebuilt native dependencies. Component hashes, the common frontend, LLVM and standard library are recorded in the manifest. [Exact inputs](exact-inputs.json)

| Actual workspace command | Control sum | Candidate sum | Median paired reduction | 95% median interval | Favorable | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `cargo build` | 5,439,530,242.5 | 4,912,570,009.0 | 9.686% | 9.649–9.719% | 12/12 | 0.00433 |
| `cargo test --no-run` | 5,298,072,658.5 | 5,001,914,530.5 | 5.552% | 5.351–5.655% | 12/12 | 0.00433 |

Cargo ran under DynamoRIO. Cachegrind counted rustc, clang and Wild. The sum uses the four images from the same command invocation. The native execution census accounts separately for the launcher and shell dispatch scripts that exec those images. The two collector groups below each use their own units, so readers can check the direction of the result independently of their relative weighting. All reductions use within-pair percentages. [Raw observations](observations.csv) · [Full process counts](processes.jsonl) · [Counter calibration](https://github.com/astral-sh/ohm/blob/0efa3139d4eb7be2344fd205d6e4dff7a0bc6c46/benchmarks/ruff-dev-loop-20261026/wild/integrated.md)

| Command | Collector group | Control median | Candidate median | Median paired reduction | Favorable |
| --- | --- | ---: | ---: | ---: | ---: |
| Build | Cargo / DynamoRIO | 1,490,653,519.5 | 1,394,430,233.5 | 6.457% | 12/12 |
| Build | rustc, clang and Wild / Cachegrind | 3,948,836,030.0 | 3,518,003,997.5 | 10.905% | 12/12 |
| Test build | Cargo / DynamoRIO | 1,112,084,385.5 | 1,012,598,843.0 | 8.947% | 12/12 |
| Test build | rustc, clang and Wild / Cachegrind | 4,186,145,062.5 | 3,989,061,740.5 | 4.648% | 12/12 |

The preregistered endpoints measure dynamic instruction counts on the warm, one-dirty-target edits. Wall-clock latency requires a separate native cohort. The tests cover the two four-process sums. The collector-group and individual-image breakdowns are descriptive. Each command ran at the workspace root with `--locked --offline`, four build jobs and CPU affinity 0–3. For each endpoint the frozen schedule used twelve pairs, balanced six control-first and six candidate-first. The interval uses the ordered paired percentages. The two-sided randomization test enumerates the 924 permitted assignments and Holm adjusts across the two endpoints. [Frozen plan](plan.json) · [Statistics and individual-image medians](statistics.json)

## Workloads and native validation

- **Build.** The checkout is Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. Setup reinstated the seven lines removed from `crates/ruff/src/main.rs` in `da8ee78491`. The measured edit removed them again. Cargo reported 501 artifacts. Only `ruff` was dirty and both arms produced the same six executable hashes for each source state. The current-source state also matches six of six hashes from the earlier native reference in this canonical workspace. [CLI patch](cli-seven-lines.patch)
- **Test build.** The measured edit reversed the exact patch from Ruff `2fb7c8ddd806aec98f8bba8f4c78d4a7c22f9d56` in both `fixtures.rs` and its snapshot. Only `fixtures` was dirty. The graph contained 619 artifacts and 102 executables. Ordinary Cargo printed 84 executable test targets, with the remaining 18 support binaries and examples also covered by the byte checks. `--no-run` stopped after building. [Historical patch](formatter-historical.patch)

The primary correctness gate compared native control and candidate output in the same workspace and target context for both source states. It required exact graph identity and 6/6 or 102/102 matching ELF hashes. Each counted command reproduced its corresponding native hashes and reported the same terminal diagnostics and target list after removing the elapsed duration and collector startup messages. The process census identified one actual rustc, clang and Wild, alongside Cargo. The mapped Cargo and compiler driver and the three Cachegrind process images were verified on each counted run. [Native executables](native-oracles.json) · [Native execution census](native-exec-census.json) · [Per-run validity receipts](gates.jsonl)

Two earlier test references provide additional comparisons. In the same canonical source-built context the current-source state matched the existing native 102/102. A separate Wild-only historical run used the published compiler and a different worktree and target directory. Its normalized graph and all 102 executable keys agree, and five raw ELF hashes agree in each source state. The registered validity decision uses the same-context control, candidate and instrumented outputs described above. [Oracle breakdown](native-oracles.json)

The original native dependency snapshot was reused by both arms. The dormant test donor initially retained the preceding one-string fixtures edit in one executable. The private copy matched all 102 donor files at copy time and recompiled `fixtures` during native preparation. Its restored current-source state then matched the full existing native reference. The two worktrees and their Git indexes were kept fixed via read-only source overlays and `GIT_OPTIONAL_LOCKS=0`.

The release and candidate used private, independent Cargo homes at one canonical pathname. Their registry proof stores contained 370 entries for build and 410 for test. The candidate also had the 32-byte verified Git-index record. Each scored command required identical receipt inventories and contents before and after, and the records remained identical across all twelve observations of each arm. Four setup probes were excluded before scoring. One lacked the host’s offline registry mapping. Three used a different native-tool search path and began unrelated dependency builds. Pinning the archived configure-time `PATH` restored the expected compiler cache context. The namespace used caller-owned ancestors so Cargo accepted both private caches. [Setup exclusions](excluded-preflights.json)

## Reproduction

Run the verifier with Python 3.11 or later. It reconstructs Cargo totals from the individual DynamoRIO thread counters, checks the three Cachegrind totals and native validity receipts, and recalculates both endpoint tests and collector-group summaries.

```sh
python3 verify.py
```

For a new run, use dedicated Ruff worktrees at the registered commit, the six binaries in the input manifest, an offline hydrated registry, the common native sysroot, DynamoRIO 11.91.20741 and Valgrind 3.22. Build the pinned DynamoRIO client and provide the path to its library. Access to the linked repositories is required. [Counter source](https://github.com/astral-sh/ohm/blob/0efa3139d4eb7be2344fd205d6e4dff7a0bc6c46/benchmarks/ruff-dev-loop-20261026/wild/counter/counter.c) · [Build and calibration instructions](https://github.com/astral-sh/ohm/blob/0efa3139d4eb7be2344fd205d6e4dff7a0bc6c46/benchmarks/ruff-dev-loop-20261026/wild/integrated.md) · [Native snapshot bootstrap](https://github.com/astral-sh/ohm/blob/0efa3139d4eb7be2344fd205d6e4dff7a0bc6c46/benchmarks/ruff-dev-loop-20261026/wild/reproduce-integrated.py) · [Four-image collector](https://github.com/astral-sh/ohm/blob/0efa3139d4eb7be2344fd205d6e4dff7a0bc6c46/benchmarks/ruff-dev-loop-20261026/wild/mixed-holdout.py)

The replay adapter uses the pinned bootstrap to warm a new dependency snapshot and the frozen pair orders for one endpoint at a time. Point `BACKEND` at `benchmarks/ruff-dev-loop-20261026/wild` in checkout `0efa3139d4eb7be2344fd205d6e4dff7a0bc6c46` of `astral-sh/ohm`. Fill in the local binary paths in `subjects.example.json`. Put the state below a private directory with trusted ancestors. Native warmup requires ample space for the two per-arm snapshots and a 24 GiB scratch reserve. [Executable paths template](subjects.example.json) · [Replay adapter](replay.py)

```sh
for action in bootstrap measure; do
  python3 replay.py "$action" build --backend "$BACKEND" --ruff "$RUFF_BUILD" \
    --state "$PRIVATE/build" --output "$RESULTS/build" --paths "$SUBJECTS" \
    --drrun "$DR_SDK/bin64/drrun" --pidcounter "$DR_CLIENT"
done
```

Repeat with `test`, its own Ruff worktree and separate state/output paths. The adapter checks the source-state digests, reruns the native ELF oracle, verifies the coverage of the Cargo caches, and saves per-pair counts in `registered-observations.jsonl`. The recorded run used a read-only source mount and the archived native dependency path. The adapter uses a fresh native snapshot and temporarily applies the two source states in a disposable worktree. The portable adapter was smoke-tested for backend loading and the exact fixture states for both commands. Its separate full bootstrap was not repeated on the measurement host. The host runner and scoring code are included alongside the raw receipts. [Recorded host runner](host/bench.py) · [Recorded scoring code](host/score.py) · [Complete raw thread counters and I-refs](counter-receipts.jsonl)
