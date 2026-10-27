# Rejected mixed-library replay

A local Ohm Cargo and rustc prototype replaced full compilation of both mixed Rust/C libraries with link-only invocations after a historical parser edit. The cached metadata retained an obsolete private crate hash. An ordinary Rust consumer compiled successfully within each output set and rejected the other set with E0460. The pilot produced no timing claim.

The checkout was Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. The reversed patch was the complete commit `3ea20f6161cbf59cb56595dfb634ec24bfa82f0b`, including the parser edit and its two fixtures. The scoped command was `cargo +ohm build --locked --offline -p ruff_wasm -p ty_wasm` on x86-64 Linux using the bundled Wild 0.11.0. It reported 362 units and 20 dirty artifacts. One baseline snapshot fed the paired replay and the full-compile baseline. All 671 reported artifact paths matched in bytes, mode and nanosecond mtime, with separate inodes.

| Tool combination | Full rustc | Link-only rustc | Immediate repeat |
| --- | ---: | ---: | ---: |
| Patched compiler and Cargo | 1 | 2 | 0 |
| Patched compiler alone | 3 | 0 | 0 |
| Patched Cargo alone | 3 | 0 | 0 |

Changing back to the unmodified compiler selected a fresh Cargo compiler namespace. Its prime ran 365 compiler processes before the zero-process original and post-edit checks. Each package's separately built Rust caller returned the same version and had identical ELF bytes in all three combinations. The original parser caller reports a t-string mismatch. The edited caller reports a bytes-literal mismatch and matches byte-for-byte across those three combinations.

The two mixed shared objects, dynamic exports and all ordered native object payloads matched. Both shared objects also passed direct symbol lookup and six zero-length allocation/free calls using wasm-bindgen's 32-bit native ABI. The remaining differences inside the standalone metadata occupied exactly one 16-byte private crate hash per library, at zero-based offsets 505532–505547 for `ruff_wasm` and 703208–703223 for `ty_wasm`. Their public hashes and stable crate IDs matched. All six subsequent forced full compiles, covering edited and original inputs with exactly the same compiler and Cargo flags as replay, produced the settled private hash for each library. Replay retained the respective cold hash.

`real.json` contains complete source and artifact SHA-256 digests, raw private-hash bytes, the selected process rosters, exported names, runtime outputs and eight ordinary bridge results. `tiny.json` records direct and transitive private-body successes, C-export and library fallbacks, both tool downgrades and foreign source-file index changes. The locally retained original raw archive and the independent tiny archive have their internal manifest digests recorded in `real.json`.

## Verify

Run `python3 verify.py` to check the manifest and assertions. To repeat the Rust-level compatibility guard, make the two edited artifact sets available independently. Each arm's search file contains one original rustc `-L` value per line, including native search paths from Cargo. Use the matching Ohm compiler/sysroot. The runner compiles two ordinary bridges, then builds a native caller against each pair of bridge and library. It checks both E0460 failures and both working combinations.

```sh
python3 check_bridge.py ruff_wasm --sysroot "$sysroot" --wild-dir "$wild" \
  --replay-rlib "$replay/libruff_wasm.rlib" --replay-search "$replay/ruff_wasm.search" \
  --full-rlib "$full/libruff_wasm.rlib" --full-search "$full/ruff_wasm.search"
python3 check_bridge.py ty_wasm --sysroot "$sysroot" --wild-dir "$wild" \
  --replay-rlib "$replay/libty_wasm.rlib" --replay-search "$replay/ty_wasm.search" \
  --full-rlib "$full/libty_wasm.rlib" --full-search "$full/ty_wasm.search"
```
