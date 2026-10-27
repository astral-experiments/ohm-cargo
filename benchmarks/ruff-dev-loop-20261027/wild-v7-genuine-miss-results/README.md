# Cost when Wild cannot reuse a Ruff link

A real Pydantic implementation change made the Wild 0.11.0 output-reuse prototype **2.04% slower** on a default Ruff workspace `cargo build`. The medians were 33.77 s with the source-matched Wild and 34.34 s with the candidate. The candidate won three of twelve pairs. The paired 95% interval for overhead was 0.16–3.83%, and the two-sided exact randomization p-value was 0.0238. Both first and final qualification traces showed twelve full rustc processes and five full links on each arm. Wild reported four misses in each candidate trace. Every immediate repeat after a measured command was fully fresh.

The plan set a 2% upper bound for miss overhead before collection. This result exceeded that bound. The same prototype earlier avoided three of five full links on a Ruff IDE test edit, reducing whole-workspace build time by 16%. Its test-build result on that edit was inconclusive. The controls used Ohm 1.99.0-14 Cargo and rustc. This evidence concerns that prototype and toolchain. [Registered workload and safety bound](https://github.com/astral-sh/ohm-cargo/blob/c977719f4247463537f6b9f978a5ce24fd4cda91/benchmarks/ruff-dev-loop-20261027/wild-reuse/wild-v7-plan.json) · [Complete source patch](https://github.com/astral-sh/ohm-cargo/blob/c977719f4247463537f6b9f978a5ce24fd4cda91/benchmarks/ruff-dev-loop-20261027/wild-reuse/patches/pydantic.patch) · [IDE edit results](https://github.com/astral-sh/ohm-cargo/tree/ddb6ffeff70f732db246319934046dedb47c535b/benchmarks/ruff-dev-loop-20261027/wild-v7-primary)

The archive retains the randomized order, elapsed nanoseconds, tool hashes, worktree checks, artifact rosters and process receipts. It also contains one exploratory comment-only pair, excluded from the estimate. Run the following in an empty directory with these files.

```sh
sha256sum -c SHA256SUMS
tar -xzf receipts.tar.gz
python3 -B analyze-native.py results-wild-package-v7-miss-build > replay.json
cmp statistics.json replay.json
```
