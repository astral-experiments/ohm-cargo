# Repeated whole compiles on ordinary Ruff member builds

Official Linux Ohm 1.99.0-16 ran `cargo +ohm build --locked --offline -j4` from each workspace member at Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. Four empty, private histories shared a canonical source, SDK, Cargo, home and separate build-directory spelling. The target was either `ruff target` or `ruff-target`. Every invocation had a successful Cargo process and the same unit, feature and output roster within its history. These observations count full compiler and Wild processes. None timed the traced commands.

| Member | Units | Unchanged build in spaced target | Unchanged build in unspaced target |
| --- | ---: | --- | --- |
| `ty_wasm` | 304 | 6 dirty units, 2 full rustcs, 1 actual Wild linker | 304 fresh, 0 rustcs, 0 Wild |
| `ty_project` | 275 | 4 dirty units, 1 full rustc, 0 Wild | 275 fresh, 0 rustcs, 0 Wild |

Each of the three repeats gave the listed result. On `ty_wasm` the repeated compilers built `ty_vendored` and `ty_wasm`, and the final output included a Linux cdylib. The crate's generated typeshed ZIP contained the exact source bytes of `stdlib/functools.pyi` in each of the sixteen completed product checks.

The original unscored cohort completed eight `ty_wasm` commands with the same counts and one successful `ty_project` build. The first `ty_project` product check stopped because the Python ZIP reader could not decode ZIP compression method 93. Its raw evidence and original failure are included. The amended cohort ran all sixteen commands from four new empty states. Deflated entries use the original verifier. Zstandard entries now pass a length and CRC-checked decode of the exact same stub. Run `python3 -B verify.py` to replay the 25 Cargo calls and 24 completed product checks. The inventory binds every original and exported byte stream.

[Original protocol](https://github.com/astral-sh/ohm-cargo/tree/471fd83ec1c1059fd726afeaaa53c513fccf6b82/benchmarks/ruff-dev-loop-20261027/spaced-ruff-member-build-discovery-plan) · [ZIP verifier amendment](https://github.com/astral-sh/ohm-cargo/tree/3023f0a5b027c838a5c59b82034cc508da89e9d5/benchmarks/ruff-dev-loop-20261027/spaced-ruff-member-build-discovery-plan-v2)
