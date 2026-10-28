# First Ruff text-size test build after adding `TextRange::to_std_range`

The first ordinary `cargo test -p ruff_text_size --no-run` took a median 2.561 s with Cargo #261 and 2.465 s with #260 applied on top. The paired reduction was 4.20% (95% bootstrap interval 1.34–7.09%). The candidate was faster in 18 of 24 pairs. The two-sided balanced randomization test gave p = 0.013122024. The statistical test passed the registered 0.025 cutoff. The lower confidence bound was 1.34%, below the 2% minimum we set for a practically significant gain. Each timed command ran alone on eight CPUs, without tracing. We restored an independent copy of the same edited-library build for all 48 commands.

All 16 declared products, including six ELF files, matched the independently verified native result. The four integration test listings matched. The separately traced, unchanged command was 11/11 fresh with zero compilers or linkers in all 48 slots. Test bodies were never executed.

[Registered comparison](https://github.com/astral-sh/ohm-cargo/tree/44c3e6db80242b5461bbb3f86f2fae5a0f166a45/benchmarks/ruff-dev-loop-20261027/rc17-text-size-first-selection-wall-plan) · [Native compiler and linker traces](https://github.com/astral-sh/ohm-cargo/tree/7ad7ac2e6d3075cf7ffb21231ec152a289e7432b/benchmarks/ruff-dev-loop-20261027/rc17-text-size-first-selection-native-results)

Re-run `python3 -IB portable.py verify /absolute/path/to/portable-result.json.gz` from the registered wall protocol to check this packet independently. The original H2 records are retained.
