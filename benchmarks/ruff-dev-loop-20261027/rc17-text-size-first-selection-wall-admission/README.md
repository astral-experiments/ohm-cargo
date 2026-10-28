# Untimed admission for the first Ruff text-size test build

After a real Ruff edit added `TextRange::to_std_range`, we built the edited library and selected its four integration tests with `cargo +ohm test -p ruff_text_size --no-run --locked --offline -j8`. Both Cargo revisions passed an ordinary first selection and a separate immediate repeat. The 16 declared files were byte-identical, including the six ELF files. The four test listings agreed in both phases. All 11 units were fresh on both repeats, which launched zero compilers or linkers. The two selections used physically independent copies of the same seed. The source and packaged rustc and Wild matched the registered versions. Each PR head passed its eight required jobs. This packet contains zero clocks.

[Registered comparison](https://github.com/astral-sh/ohm-cargo/tree/44c3e6db80242b5461bbb3f86f2fae5a0f166a45/benchmarks/ruff-dev-loop-20261027/rc17-text-size-first-selection-wall-plan) · [Native compiler and linker traces](https://github.com/astral-sh/ohm-cargo/tree/7ad7ac2e6d3075cf7ffb21231ec152a289e7432b/benchmarks/ruff-dev-loop-20261027/rc17-text-size-first-selection-native-results)

Re-run `python3 -IB portable.py verify /absolute/path/to/portable-admission.json.gz` from the registered wall protocol to check this packet independently. The original H2 records are retained.
