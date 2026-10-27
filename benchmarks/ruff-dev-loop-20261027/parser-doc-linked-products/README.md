# Which native links changed bytes after two Ruff edits

The same eight linked binaries or shared libraries changed after each replay of the parser diagnostic edit under `cargo build`. On `cargo test --no-run`, 58 of the 67 linked outputs changed in both replays. Nine were byte-identical, including their build IDs. The private comment edit had a different effect. [Historical patches, full workspace results and release subjects](https://github.com/astral-sh/ohm-cargo/tree/2f07518331735487c84aaeadab58ce98d7c5a71b/benchmarks/ruff-dev-loop-20261027/native-qualified-results)

| Ruff edit and command | Wild processes per replay | Byte-identical linked outputs in the first replay | Byte-identical linked outputs in the final replay | Other recorded ELF sections changed in the final replay |
| --- | ---: | ---: | ---: | ---: |
| Private doc, `cargo build` | 3 | 3 | 3 | 0 |
| Private doc, `cargo test --no-run` | 19 | 19 | 17 | 0 |
| Parser diagnostic, `cargo build` | 8 | 0 | 0 | 8 |
| Parser diagnostic, `cargo test --no-run` | 67 | 9 | 9 | 58 |

The private doc replay rebuilt the `ruff`, `ruff_dev` and `ruff_wasm` build outputs. All three stayed byte-identical. In the final test replay, `ruff_server`’s `document` test and `ruff_wasm`’s `api` test differed in the GNU build ID and the `.rodata` section-header entry size. Every other recorded ELF section field matched for these two outputs.

The nine unchanged parser test products were Ruff's `analyze_graph`, `config`, `direxist_guard` and `resolve_files` tests, `ruff_python_formatter`'s `normalizer`, both wasm packages’ `api` tests, and ty's `cli` and `self_environment`. Each product matched in both comparisons. Rust code that safely skips a job must establish eligibility from current inputs before invoking the compiler or linker. These byte comparisons measure which products warranted that investigation. [Search-path and compiler-driver counterexamples](https://github.com/astral-sh/ohm-cargo/tree/9c8bedf3826d07553853e6d186eb1039878f6b66/benchmarks/ruff-dev-loop-20261027/native-link-search-controls)

Each comparison uses original source from the same arm and the associated edited state. The first pairs the initial warmed source with the first traced edit. The second pairs the last traced edit with its restored source. The export records Wild's successful `execve`, the `-o` operand and the published raw event digest. The verifier binds that exact event to one Cargo artifact. It checks raw SHA-256 and individual ELF section fields, and checks every workspace ELF that changed belongs to a traced linker. The environment is the original matched #233 compiler experiment. The corrected #254 Cargo replay independently reproduced all four full rustc, link-only rustc and Wild rosters. [Fixed Cargo process replay](https://github.com/astral-sh/ohm-cargo/tree/855211cdb928f7fc425cba091795738c248f0527/benchmarks/ruff-dev-loop-20261027/corrected-native-rerun-results)

Run `python3 -B verify.py` in this directory. The script reads the four original archives from the sibling `native-qualified-results` directory. To use a separate copy of those immutable files, pass the directory as an argument.
