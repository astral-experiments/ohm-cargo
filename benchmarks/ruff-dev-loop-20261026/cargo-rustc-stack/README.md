# Combined Cargo and rustc on a parser source edit

Ruff’s full `cargo check -p ruff_python_parser --locked --offline` used **1.66% fewer instructions** with four Cargo PRs and the early-lint-scope rustc change. Both the parent and treatment used release-profile PGO Cargo builds and release-recipe stage-2 PGO/BOLT compilers. Every paired build saved instructions and all eight randomized four-run blocks favored the treatment (two-sided exact block randomization p = 0.0078125). The range across 16 pairs was 1.47–1.79%.

| Scope | Parent median instructions | Treatment median instructions | Median paired reduction |
| --- | ---: | ---: | ---: |
| Cargo and rustc | 1,160,647,455 | 1,141,376,403 | 1.66% |
| Cargo | 288,394,621 | 274,596,846 | 4.79% |
| rustc | 872,252,834 | 866,746,230 | 0.62% |

The Cargo source, exact four-change patch, and build profile are in the [cumulative Cargo benchmark](../cargo-stack/). Rustc compared `f1a7cf9d20b2cae39e991b178b56ba06b43dc8fa` with the empty-lint-scope change. The parent and candidate were compiled with the same release-recipe PGO and BOLT data. [rustc PR and standalone measurements](https://github.com/astral-sh/ohm-rust/pull/230)

Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. Change `Invalid Syntax` to `Invalid syntax` in the parser’s `crates/ruff_python_parser/src/lexer.rs`. Prepare a full pre-edit snapshot of the target and shared build state. Use the same Cargo executable path and rustc sysroot path for both arms. Warm the actual instrumentation environment until A/B/B/A/B consecutive pre-edit invocations show zero dirty units. Before every scored arm clone the immutable snapshot, replay the edit, and measure under Callgrind with child tracing. Counterbalance the two orders independently in each four-run block.

Each of the 32 samples had 90 artifact records, only the parser library rebuilt, and exactly one Cargo and one rustc process. All samples emitted identical metadata (`ab5a86947c6c15f40e21848fc8ee5352ba6582c6b9647f8ca0c2290ef22ebadf`) and public API hash files (`a756da8a134662003d47f782811f43721c4e7534db824cea97c499c00e4bb547`). The CSV lists every process count.

| SHA-256 | Parent | Treatment |
| --- | --- | --- |
| Cargo executable | `211465de4b9e4589da2be06871acd9304dd3b94c849c1304f723484cb4f71dfc` | `9346a13cd66ec30b9bc369f12bb305ff943eb6ec9ff15f47646ab74f784f8e60` |
| rustc driver | `539e8623c70298849aa3043f35374ea3c7dc7215aac44011e64fccdc818f91a4` | `c1243f1a3421d45c20baf875cb4bff79a696c35e0a714dfddcdf2e47fbe03220` |
