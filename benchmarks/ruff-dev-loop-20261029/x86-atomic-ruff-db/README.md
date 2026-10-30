# One fewer rustc invocation on the Ruff build and test loop

After a real change to Ruff’s directory-removal error, the parent compiler rebuilt `portable_atomic` on each unchanged visit. The candidate recognized the crate’s x86-64 assembly as file-free. Every one of eight fresh paired installations produced the same process counts.

| First unchanged visit after the edit | Full rustc, parent → candidate | Link-only rustc | Stock Wild links |
| --- | ---: | ---: | ---: |
| `cargo build -p ruff_db` | 3 → 2 | 0 → 0 | 1 → 1 |
| `cargo test -p ruff_db --lib --no-run` | 4 → 3 | 0 → 0 | 2 → 2 |

A balanced, randomized compiler order gave a two-sided exact p-value of 2/70 (0.0286) for each preregistered endpoint. Both endpoints used the same eight pairs. The counts cover 320 normal Cargo commands and 230,001 process trace files. No test execution contributes to the measured counts. No wall-time inference was made.

The real edit also removed one full compilation on both commands. A downstream program changed from `Other` to `DirectoryNotEmpty`. Ruff’s affected test went from failing to passing, both neighboring cases stayed green, and all 130 test names matched. Each edited binary and each reverted binary matched its own independent reference byte for byte. The invalid edit returned E0425. On a second Linux x86-64 machine, the public replay below reproduced both primary counts across another 40 commands.

The parent is `ad005f99d0b51fd62b5c237bc13b31b371a1686e` and the child is `b9b4105463dd4a9a16f39509d868aa15d5f96e00`. Both used Cargo `84af87848a5a952ba61ae6a2cc5b22da24130200` and stock Wild. The matched compiler builds had 119 identical bootstrap commands and 53 identical standard-library files. Only the compiler driver differed. Ruff was `93526150df078af7dd8fc4226cdcc469539d2001` and the historical edit was `11a6493c944a9b78ebc72fa0b792ab706eae093a`.

The paired protocol, ordered installations and digests of the original registration are in this directory. The independent verifier checks the physical job projections, product hashes, test inventories, invalid verdicts and exact permutation test. Its self-test also rejects four deliberate corruptions. The native-input controls cover file-backed generic assembly, changed bundled archives and implicit native library search. The sibling `x86-atomic-ty-server` directory contains the real e2e edit, provider experiment and clean ELF comparison.

Verify the published observations with Python 3.11 or later.

```sh
sha256sum --quiet -c SHA256SUMS
python3 -IB verify.py observations.json.gz --self-test
```

To reproduce on Linux x86-64, select either source-matched SDK as the `+ohm` toolchain. Use an offline Cargo registry containing Ruff’s locked dependencies, a full Ruff checkout with both commits and an unused directory on a filesystem with at least 8 GiB free. The script invokes ordinary Cargo and records the compiler and Wild processes with strace. Repeat at the same logical paths with the other toolchain in a separate empty environment.

```sh
python3 -IB rerun.py --ruff "$PWD/ruff" \
  --registry "${CARGO_HOME:-$HOME/.cargo}/registry" \
  --work "$PWD/ruff-x86-atomic-replay"
```

Both source revisions also inherit a separate issue when a retained object is overwritten in place through an incremental hard link. That issue blocks release qualification. The unchanged and genuine-source-edit measurements here did not modify build artifacts.
