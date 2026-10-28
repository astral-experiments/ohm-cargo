# Four duplicate integration-test builds after a real Ruff edit

After adding `TextRange::to_std_range` and building the edited library, both Cargo versions selected the same 11 units for `cargo +ohm test -p ruff_text_size --no-run`. The control compiled and linked each of the four integration harnesses twice. The scheduler fix compiled and linked each once. Both independent selections on each Cargo version agreed. [Registered native experiment](https://github.com/astral-sh/ohm-cargo/tree/d45eb59141a0913ca429f6b44a56b9adf68ea35d/benchmarks/ruff-dev-loop-20261027/rc17-text-size-first-selection-native-plan)

| First package test build | Full rustc processes | Actual Wild links | Integration harness compiles and links |
| --- | ---: | ---: | --- |
| Cargo #261 | 14 | 10 | Two each for `auto_traits`, `constructors`, `indexing` and `main` |
| Cargo #261 and #260 | 10 | 6 | One each for the same four harnesses |

All six declared ELF products were byte-identical across arms. All four test listings matched, covering ten tests. Each untouched repeat reported all 11 units fresh and launched zero compilers or linkers. No test bodies ran. The older library rejected a direct call to the new method with E0599. The edited library returned `1..4`. The benchmark used the two matched release-profile Cargo executables with the official Ohm 1.99.0-17 rustc and Wild.

Run `python3 -IB verify.py` to recompute the counts from successful PID records, recheck their argument hashes against the original trace receipts, compare the actual declared outputs and verify every harness listing. Private registry directory names are replaced in the portable argv. Original hashes and raw traces are retained on the qualification host. The experiment collected zero timing observations.
