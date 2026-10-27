# First-occurrence build and test compilation for three Ruff parser edits

The experimental Cargo and compiler can avoid native code generation for two mixed Rust/WebAssembly libraries on two of the three historical edits. Both arms use the same release compiler. The control uses #254 Cargo. The candidate uses the additional guarded native request. Each guarded compiler process still performs a link.

| Historical Ruff edit | Full compiles, build | Full compiles, test compilation | Wild links, build / test |
| --- | ---: | ---: | ---: |
| Remove redundant lexer indentation write | 35 → 35 | 93 → 93 | 8 / 67 |
| Validate signed match patterns | 3 → 1 | 6 → 4 | 8 / 67 |
| Avoid single-string allocation | 3 → 1 | 6 → 4 | 8 / 67 |

Every count held on the first source reversal and its restoration. In the two improving rows the candidate still ran two guarded compilers in addition to the remaining full compiles. Both arms also ran 6 ordinary link-only jobs on build and 62 on test compilation for these two edits. The signed-pattern reversal removed both expected Ruff diagnostics. The complete 501- and 619-unit immediately following commands did zero compiler or native-link work. The matched workspace executable rosters and CLI diagnostics passed. For these first test reversals the cross-arm raw ELF equality counts were 109/110, 105/110 and 106/110. Every remaining file was byte-identical after masking only the GNU build ID descriptor and the .rodata section-header entry size.

All independent Rust readers succeeded under the same arm that produced their inputs. Crossing the independently built registry dependencies produced E0460. A separate full/full control and eight repeated identical rustc invocations traced this to a third-party procedural macro's randomized output ordering. [Full/full controls and rejected timing qualification](https://github.com/astral-sh/ohm-cargo/tree/2574186849c7a41c9bc6d29698ef3101af5909d9/benchmarks/ruff-dev-loop-20261027/mixed-qualification-rejection-h3-v2)

The lexer's apparent private edit does move an externally observable source position. Three fresh ordinary Rust compilers used the captured parser metadata, matching lexer source and a caller passing zero arguments to the public lexer. Each emitted E0061 at the same caller position. Its definition note reported lexer.rs line 1623 on original Ruff, 1620 on the edit and 1623 on restoration. That observation alone does not identify which of the 35 or 93 full compiles read that position.

Run `python3 -B verify.py` to reopen the two payloads, reconstruct process and ELF controls, and verify raw rustc diagnostics against their actual metadata and source digests. These first-occurrence runs cover process counts and behavior. They do not estimate wall-time speedup. [Frozen source selection](https://github.com/astral-sh/ohm-cargo/tree/7ef4e84e3838cabd8e713fcadef6347a67f9fc00/benchmarks/ruff-dev-loop-20261027/first-occurrence-parser-plan) · [Frozen runner](https://github.com/astral-sh/ohm-cargo/tree/f66491bfe3af4ff03fdd4c40652136b601dfc6fc/benchmarks/ruff-dev-loop-20261027/first-occurrence-parser-runner-v2)
