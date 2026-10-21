# Unit-path caching on the restacked PR179 source

This independent supplement validates the ported path cache against the exact
restacked PR179 revision. It does not reuse or pool the original PR175 samples.
Both fixed confirmations pass the predeclared Cargo instruction-count gate:

| Unchanged uv workload | Cargo instruction reduction | 99% paired bootstrap interval | Wins |
| --- | ---: | ---: | ---: |
| Full-workspace `cargo check` | 1.571362% | 1.457107–1.632101% | 12/12 |
| Full-workspace `cargo test --no-run` | 1.553731% | 1.460425–1.596393% | 12/12 |

Each workflow has twelve independently randomized, balanced AB/BA pairs plus
two excluded warmup pairs. Both exact two-sided sign tests give p=0.00048828125;
both order-specific effects are positive. The gate requires at least 1% point
reduction, a positive lower bound of a 99% paired bootstrap interval, sign
p<=0.01, and positive effects in both orders. All samples are retained.

The claim is fewer Cargo userspace instructions during a fresh, warm dev-loop
invocation. No uv test executes. These observations do not establish a native
wall-time gain, a dirty-build gain, or faster test execution. Callgrind excludes
compiler/linker/build-script child work and kernel instructions. Both variants'
allocator-fallback warnings remain in the raw logs.

The source pair is:

| Variant | Source commit | Source tree |
| --- | --- | --- |
| Baseline | `19718e6d1637244ffbb193334f50bae3ffca1be5` | `f4ce59f92aa17461fe3c8b68923c88539136045a` |
| Candidate | `c40676e264501bc8a93095d3a273a1c300b80875` | `0a392258c801cff734d223a3f9af73d5b5a4e3c0` |

The measured stripped binaries are `c165e35dcd0233b6b6e15d81c2bbd6ba19cd07de1352ca63614f27240edcd3c2`
and `179f17531a2e9a3475c58965ad4a82248d8eb4af5ce8f1bbfe3d6be5632de86d`.
Both came from one matched production-settings cohort: one source/target
location, compiler, build environment and embedded Cargo HEAD. The cohort also
contains a PR176 control for a separately declared cumulative experiment. Its
build provenance is included; its measurements are outside this supplement.

The cache stores unit-hash strings and output-directory paths. If trusted
shared-cache preparation falls back, cached directory paths are cleared while
stable hash strings remain. PR174 moved that fallback into
`prepare_shared_context`; the port clears `self.unit_paths` at that location.
The sole changed added/removed line relative to the original patch is that
receiver adjustment. The exact port patch and full source patches are included.

[Historical original-PR175 evidence](https://github.com/astral-sh/ohm-cargo/tree/35a2d7792848c3c45fffdcd7d4308d8d79d98ba4/benchmarks/uv-dev-loop-20261021/path-cache)
retains earlier exploratory results, the failed profiler setup attempt, both
inconclusive native confirmations, and correctness attempts. Those native
results remain inconclusive and are not evidence of a current-stack wall-time
gain. A separately frozen four-change native experiment does not supply any
result to this supplement.

See [REPRODUCE.md](REPRODUCE.md) for the statistical method, exact commands and
new-prefix requirements; [VALIDATION.md](VALIDATION.md) distinguishes source CI,
production binary checks and historical coverage. `SHA256SUMS` binds every
packaged text file and the raw archive. `RAW-MANIFEST.json` binds every archive
member. Full attribution profiles remain in the task workspace; their exact
counter lines, hashes and sizes are packaged in `callgrind-counter-extracts.jsonl`.
