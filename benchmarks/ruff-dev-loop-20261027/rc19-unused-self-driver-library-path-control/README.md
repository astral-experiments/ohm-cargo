# GNU LIBRARY_PATH changes a real Rust integration executable

The published -18 package, source-stamped Cargo `34dad66f` with Rust `5e3de497`, and the Cargo-managed native search fix `2d04af1e` all return the old program after an ordinary public Rust source edit. The crate has no build script, dev dependency, custom rustflags or compiler wrapper. Its integration test calls a real C function via a normal Rust `#[link]` declaration. The two absolute, private directories in GNU `LIBRARY_PATH` stay unchanged throughout. GCC forwards each path explicitly to the linked executable’s real linker as an ordered `-L`.

| State | Ohm defaults, all three tested images | Same candidate with defaults off |
|---|---|---|
| First, only fallback archive exists | 17 | 17 |
| Add a public Rust struct and create earlier regular archive | 17, no reader Rust/link job | 29, real reader compile/link |
| Evict only reader executable, rerun same command | 29 | 29 |
| Independently empty target and shared store | 29 | 29 |
| Restore library source, corrupt earlier archive | Cargo succeeds, old program still 29 | Cargo 101, native error |
| Force reader, or use a second empty store | Cargo 101, native error | Cargo 101, native error |
| Remove malformed archive | 17 | 17 |

The qualifying comparison includes an ordinary initial unchanged command, all native statuses, source and executable SHA-256, the kernel-level driver argv commitments, the actual relative earlier/fallback search order, and both separately empty stores. The ground truth consists of executing each successful integration test and its integer printed directly by the native function. No linker or compiler implementation changed during a run. Both stock and candidate real default linkers are stock Wild. Disabling Ohm defaults uses the host GNU linker. Stock Wild also independently demonstrated both clean 29 and the genuine malformed failure on every default arm.

This result is separate from Cargo’s propagated `rustc-link-search` from a build script. The `2d04af1e` source change covers that case. The earlier native directory in this fixture enters at the GCC driver, after rustc and Cargo construct the command. The old native manifest explicitly records that the self-library is unused.

`python3 -IB reproduce.py SDK EMPTY_PATH --expect skip` runs the fixture with a private Rustup alias, source, `CARGO_HOME`, three independent target/shared states, and native archives. The directory must not exist and `cargo` must be a Rustup proxy. Add `--defaults-off --expect relink` for the comparator or use `--expect relink` to check a repair. Requirements are Linux x86-64, GNU cc/ar and strace. `python3 -IB verify.py` performs the offline verification.
