# Native confirmation on the released eighth host

Recorded 2026-10-21 03:29 UTC, before any candidate has been run or measured
on this host. The external benchmark coordinator released charlie-oss-8 at
03:20. Read-only occupancy inspection found no compiler or benchmark workload;
the coordinator was copying its completed evidence. Its directories remain
untouched. All task writes use a new isolated root:
`/tmp/ohm-hillclimb-20261021/native-pr175-confirmation`.

This scheduling decision lets the separate full native-build-to-check loader
experiment continue on host4. It does not change the publication gate or
discard any earlier host4 measurements. Results from different hosts, baselines,
or Cargo build settings are not pooled.

Native confirmation uses the frozen repeated runner (SHA256
`50547460e030aa73e1f48121bf477cf8f4a4538bf1bb577851af54176750b6d3`),
30 paired groups, two warmup pairs, and eight fresh invocations per variant
group. The group remains the statistical unit. CPU affinity is 0-7 and Cargo
uses eight jobs, though validated warm commands must launch no compiler,
build-script, linker, or test child. Both variants occupy one canonical Cargo
path and use the same pinned uv source, compiler, paths, caches, and environment.
Test workloads are strictly `cargo test --no-run`.

Seeds: output-remap check 2026102116, output-remap test 2026102117;
lazy-Git check confirmation 2026102124, test confirmation 2026102125;
path-cache check confirmation 2026102126, test confirmation 2026102127.
Any optional eight-pair lazy-Git native exploration uses 2026102123 and is
reported separately. Fixed batches finish without effect-based stopping.

The existing 99% paired bootstrap, exact two-sided sign test, minimum 1%
improvement, and positive estimates in both orders govern a native timing
claim. A reproducible Cargo-instruction claim may be published after its
independent fixed confirmation and correctness/regression validation even if
native timing is inconclusive; the PR must say so explicitly.

The baseline is PR175 applied to the pinned 5e5d271 Cargo source, compiled with
all-static/ohm-defaults, ThinLTO, one codegen unit, debug level 1, and no PGO.
Candidates use the same source and target directories, compiler, and flags.
All runtime inputs, binary/source/strip metadata, the CA bundle, and resolved
dynamic libraries are hashed. No host security or global configuration changes
are made. The original normal-build results remain separate exploratory data.
