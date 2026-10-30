# Current full Ruff CLI native admission

Twelve unscored builds used one physical compiler at Rust `08d49cba6aacb0cac27a96eea335ed1c7439f483`. Each setting independently produced a clean CLI on both real Ruff branches. The first feature visit and both branch returns reproduced their own setting's entire clean executable and linked reader. Every switch issued 20 genuine rustcs and one stock Wild. Each unchanged repeat issued zero. The 375-unit graph, Rust reader, CLI version, accepted input, E711 diagnostic, actual fix, clean recheck and invalid-syntax rejection passed.

The two options emit different raw CLI bytes. The exact GNU link commands name different Cargo build directories for the same native jemalloc dependency. On each branch the only different string in the complete DWARF string table was that one observed directory. A complete ELF comparison verified every executable section, four loadable segments with only the 32-byte build ID masked, and all raw bytes outside the three changed nonloaded debug sections and the build ID. An independent decoder read both entire debug information and macro streams with one literal build path substitution.

| Genuine branch | CLI bytes each | Equal bytes outside the four fields | Debug information lines each | Macro lines each |
| --- | ---: | ---: | ---: | ---: |
| Original A | 149,933,440 | 94,177,808 | 15,551,948 | 68,285 |
| Feature B | 149,789,624 | 94,056,598 | 15,528,403 | 68,285 |

The reader itself remained byte-identical across the two options on each branch. It reported `Expr=64 valid=1 rejected` on A and `Expr=56 valid=1 rejected` on B. The same-option equality checks include every debug byte and the original build ID.

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py` to verify the projection. `project.py` reopens the native and decoded receipts. The complete comparison, source binding and decoder commands are in the immutable registration. This packet supplies zero elapsed observations. [Registration and executable verifier](https://github.com/astral-experiments/ohm-cargo/tree/e91f82ceeeb9bc377dd0efbc66d3f509552d66a2/benchmarks/ruff-dev-loop-20261030/branch-switch-incremental/storage/alternatives/switch-only/full-cli-timing/registration)
