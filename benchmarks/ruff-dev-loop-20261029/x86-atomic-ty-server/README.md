# Safe x86 atomics on the real Ruff ty_server test

Both compiler images passed the same 15 ordinary Cargo visits. On each of two unchanged runs the W compiler ran four full rustcs and the X compiler ran three. The missing process was `portable_atomic`. Both still compiled `build_script_build`, `unicode_names2` and the `e2e` test target, and both still ran two stock Wild links, including the actual e2e link. Neither used link-only rustc. This separate correctness replay has no timing or instruction-count endpoint.

| Matched result | W/K | X/K |
|---|---:|---:|
| Units in each successful Cargo result | 300 | 300 |
| Full rustcs on each original and edited independently empty build | 303 | 303 |
| Wild links on each of those builds | 48 | 48 |
| Fresh units on each unchanged repeat | 277 | 283 |
| Full / link-only rustcs on each unchanged repeat | 4 / 0 | 3 / 0 |
| Wild links on each unchanged repeat | 2 | 2 |
| Valid provider, both ordinary and forced | exit 83 | exit 83 |
| Malformed provider, both ordinary and forced | Cargo 101 | Cargo 101 |

The genuine edit reversed Ruff `1b9310471b7d1178633e58ee63808522609db887` on `93526150df078af7dd8fc4226cdcc469539d2001`. The historical inlay-hints test then checks the alternate builtins reference. Both notebook cases and the actual inlay assertion ran on each healthy result. The native body contained only the expected source snippet, a new compiler caller used both `ruff_db` and `ruff_python_parser`, and the full test listing contained exactly 200 entries. The invalid edit returned E0308 at line 22 without linking the e2e program. [Ruff change](https://github.com/astral-sh/ruff/commit/1b9310471b7d1178633e58ee63808522609db887).

Each independently empty edited target and shared store produced the same full 212,707,704-byte ELF as its own warm edit. Both compilers also agreed on that full file, SHA-256 `ed71b77cf8d7fdfb416a3ab5e0ad2c0f357b8c2758429af8f2af36d4f06b7703`. The original executable had SHA-256 `c1d00a2b901061606607e500f37c17ad053dd1142cd16d3eafd53cf6a01fb103`. The private native provider produced SHA-256 `3fccf264b86cb0fadfcd0dbcff7efbaaccc767fcc2b041e88bf195e33d4b1a2f` and made the actual executable exit 83. Its malformed replacement produced the real Wild script error. Both removal visits recovered the original ELF. The case used the executable-specific `.preinit_array` provider in the psm build output before `-lgcc_s`.

The source-qualified W and X Rust commits were `ad005f99d0b51fd62b5c237bc13b31b371a1686e` and `b9b4105463dd4a9a16f39509d868aa15d5f96e00`. Both ran the same Cargo K `84af87848a5a952ba61ae6a2cc5b22da24130200` and the stock Wild executable. All 2,453 SDK files were verified in each arm. Only the compiler driver differed. Both arms used the same canonical source, SDK, target and shared paths, each on a new isolated filesystem. The experimental Cargo and compiler images are distinct from a hosted release package. [Cargo source](https://github.com/astral-sh/ohm-cargo/commit/84af87848a5a952ba61ae6a2cc5b22da24130200).

## Verify or replay

```sh
python3 -IB verify.py --self-test
python3 -IB rerun.py --help
python3 -IB verify-raw-arm.py --help
```

The two compressed observations contain all 30 visits, physical compiler names on warm cases, complete tool identities and output commitments. The independent raw verifier reconciles every successful exec and resumed syscall, validates the selected native argv and library-search order, rechecks individual source/error/runtime outputs, and compares incumbent and independent edited file bodies in full. Full private originals and three ELF bodies were compressed and re-read. Their public commitments and sizes appear in `custody.json`. The original administrative launcher had a malformed procfs reference and stopped before Cargo. Both prospective corrections and its stderr are retained in the raw custody.

For a new local specimen, use a full Ruff Git clone containing both pinned commits, a complete Linux x86-64 Ohm SDK, the offline registry and an empty work directory with at least 9 GiB of disk and sufficient OS headroom. The original guarded each 12-GiB target area and kept more than 16 GiB of OS memory available. The execution used Python 3.11+, Git, rustup, strace and GCC.

```sh
python3 -IB rerun.py --ruff "$PWD/ruff" \
  --registry "${CARGO_HOME:-$HOME/.cargo}/registry" --work "$PWD/ty-e2e-fresh"
```

The adapter creates its own checkout and two independently empty target/shared generations, uses normal `cargo +ohm test --locked --offline --no-run -j4 -p ty_server --test e2e --message-format=json`, chooses the psm directory from the genuine stock Wild argv, and preserves the ordinary, forced, malformed, recovery and independent clean results. For two-image comparison repeat at the same logical paths with separate private states and each intended compiler behind the same `+ohm` alias. Local artifacts and counts belong to that independent run. The H8 enrolled driver additionally captured the coherent caller and every full vs link-only process for the published comparison.
