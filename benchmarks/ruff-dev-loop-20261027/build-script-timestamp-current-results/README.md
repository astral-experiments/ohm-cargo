# Independent current-release Ruff workspace check

This is a separate confirmation with a newly cold workspace state, a fresh randomized order, and the full Linux Ohm 1.99.0-16 compiler/standard library/Wild. Its 24 pairs and their inference are independent of the earlier d38fdd025 study. The two Cargo binaries used PGO release builds of the distributed 4c07cbf6 parent and proposed db24aef8 fix, with verified matching LLVM packaging.

| Endpoint | Control median | Fix median | Paired reduction (95% interval) | Holm p |
| --- | ---: | ---: | ---: | ---: |
| Changed check | 1.433 s | 1.374 s | 3.56% [-2.03%, 8.86%] | 0.211226 |
| First untouched check | 1.000 s | 0.619 s | 35.73% [28.91%, 41.78%] | 9.37014e-06 |
| Changed plus first untouched | 2.476 s | 2.076 s | 16.75% [13.61%, 20.08%] | 7.0276e-06 |

Each arm ran the ordinary check on Ruff 93526150df with all three build scripts from historical a8ba9e0458 reversed or restored, followed by two untouched checks. The primary family is the edited check, the following check, and their sum. Every pair began from its own independent fully fresh snapshot. The separate physically traced comparisons contain all 520 artifacts, typed compiler and linker launches, and the genuine changed-script executables. The generated Pydantic witness and changed directive, source, macro and native input cases were run alongside. These measurements cover checks following build-script changes.

Run `python3 -B verify.py` to verify all 144 untraced clocks, the 48 fully fresh episode starts, and the three adjusted tests. The second untouched check was descriptive only, and each reported median describes one arm. The paired effect uses log ratios. See `audit.json` for direction-specific admission and physical post-study calibration and `analysis.json` for every paired row and endpoint.

[Preregistered plan](https://github.com/astral-sh/ohm-cargo/tree/f112ad3394f13bd6d430ddf5598f84255bedc138/benchmarks/ruff-dev-loop-20261027/build-script-timestamp-current-confirmation-plan) · [Release and runner binding](https://github.com/astral-sh/ohm-cargo/tree/cc5f9902115d6349d3fbd487daeaa63fa89cc68e/benchmarks/ruff-dev-loop-20261027/build-script-timestamp-current-release-binding) · [Previous independent result](https://github.com/astral-sh/ohm-cargo/tree/d2c97843566dc2c675a043aec8ab751e7a3bae75/benchmarks/ruff-dev-loop-20261027/build-script-timestamp-timing-results)
