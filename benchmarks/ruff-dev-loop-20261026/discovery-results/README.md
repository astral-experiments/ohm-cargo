# What rebuilds after six historical edits

The six discovery patches were chosen by a fixed hash rank from Ruff history. Each complete patch was applied in reverse to the pinned Ruff revision in a disposable linked worktree. All six commands compiled successfully and restored the original worktree. The five held-out patches were excluded from this survey. [Selection rules and complete patches](../entropy-corpus/)

| Discovery edit | Unqualified command | Reported artifacts | Dirty artifacts |
| --- | --- | ---: | ---: |
| Lint rule documentation and fixture `c2b2eda972` | `cargo check` | 520 | 11 |
| Parser error recovery `0ecff87790` | `cargo check` | 520 | 35 |
| Formatter representation `1fcdb82be0` | `cargo build` | 501 | 20 |
| Python standard library API `103168bd42` | `cargo test --no-run` | 619 | 58 |
| Server diagnostics and notebook tests `f304bc0cac` | `cargo build` | 501 | 4 |
| Formatter test harness `2fb7c8ddd8` | `cargo test --no-run` | 619 | 1 |

For the linter and parser edits, an additional verbose pass captured the actual compiler executions. All 11 and 35 dirty artifacts launched rustc, respectively. The parser change was a 20-line edit to the body of a parser method, accompanied by a Python fixture and snapshot. Comparing the public API fingerprints associated with emitted metadata showed that 28 changed in the parser run and seven changed in the linter run. The first number for each command is the complete workspace roster, including fresh dependencies.

`fanout.json` includes the full dirty-target lists. The survey recorded Cargo-only instructions with DynamoRIO and native compiler and linker execution. Its single elapsed observation per edit is diagnostic and carries no wall-time performance claim.
