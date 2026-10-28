# Incremental module children after a public identifier moves

On Linux x86-64, Ohm 1.99.0-17 panicked on the second unchanged-reader workspace build when an upstream crate produced both an rlib and a cdylib. Adding a private module before a public function moved its identifier 11 columns. The public hash stayed the same, while the reader recomputed a different fingerprint for `module_children(input)`. An independent empty target built the same edited source and printed 29.

The ordinary three-command reproduction is `python3 reproduce.py --expect parent` with the installed -17 toolchain or `python3 reproduce.py --expect fixed` with the patched compiler. The script uses `cargo +ohm build --workspace --offline --quiet` with separate target and build stores. `python3 verify.py` checks the recorded measurements, scope controls and source patch. No wall-time estimates were collected.

## Compiler inputs and results

The candidate applies `compiler.patch` to Ohm Rust `bfa236f639034f61ec884c15bd1f4e0b75e508ac`, compiler subtree `df7ace004eab417c044fe62927c673daefd2b208`. It hashes the parentless diagnostic identifier span into its owning definition using the existing metadata-table machinery. This covers directly declared module children. It also enables the existing exact native spelling-location guard for codegen output containing Rust metadata, including rlib plus cdylib and Rust dylib. Standalone cdylib and staticlib contain no metadata that can satisfy a Rust reader's dependency. No new reachability edges are added.

| Native compiler | Driver SHA-256 | Warm default mixed library | Empty edited build |
| --- | --- | --- | --- |
| Published -17 | `618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7` | panic, exit 101 | 29 |
| Matched release-source parent | `52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955` | panic, exit 101 | 29 |
| Matched release-source fix | `748e5862ece9b0e3098cdae472e1b0d94c50da724b8438f2e267c9007aee8737` | 29 | 29 |

All native arms ran the installed -17 Cargo `4e406539…`. The two source-built arms used frontend `4fa9a18b…` and the same PGO/BOLT recipe. The distribution used its own frontend `7ec52638…`. The native Rust tests ran on Linux. The two checked-in regression sources are also suitable for the repository’s macOS run-make job.

Nine distinct warm cases panicked on both parents and passed on the final compiler. They cover the dual library, a move caused only by leading spaces, Rust dylib, combined Rust/native library outputs, and forced metadata-only callers. The remaining controls include the same unmodified identifier position, a real private implementation change, default behavior for a pure rlib, disabled Ohm defaults, explicit public hashing opt-out, and empty incremental state. Requesting a standalone cdylib or staticlib as a Rust dependency failed from the first build on all arms. A pure Rust dylib linked and ran with the matching dynamic standard library. Its ordinary static-standard-library configuration failed to link on all arms. The new run-make tests progressive return values 17, 29 and 31, pure metadata-only compilation, and a change in the native mixed producer hash after a 256-column move. Three existing Ohm private-definition run-make tests also passed on the fix.

## Retained Ruff cutoff

The matched release-source arms each built Ruff `93526150df078af7dd8fc4226cdcc469539d2001` from an independently empty target and build directory using `cargo +ohm build -p ruff --bin ruff --locked --offline --message-format=json -j4`. Two historical changes were wholly reversed and restored. The 373 units cover this CLI's dependency graph.

| Real edit or restoration | Cargo units marked fresh | Physical full rustcs | Physical link-only rustcs | Wild links | Immediate unchanged build |
| --- | ---: | --- | --- | ---: | --- |
| `0ecff87790`, private parser recovery | 357/373 | 1, ruff_python_parser | 1, ruff | 1 | 373/373, no rustc or Wild |
| `36029f1c9a48`, private RUF008 helper documentation | 366/373 | 1, ruff_linter | 1, ruff | 1 | 373/373, no rustc or Wild |

Both arms retained the affected producer public hashes within each edit and restore. The parser edit changed the CLI bytes and removed the two actual signed-pattern errors. Restoration reproduced the exact prior CLI bytes and restored the diagnostic ranges at line 2, columns 11–15 and 11–14. The doc edit kept the exact CLI bytes and the two RUF008 diagnostics. Each observation ran a native executable. The parser diagnostics for the matched parent were also checked in a second full edit/restore sequence. Between compiler images, their initial CLI bytes differ. In the process data a Rust primary input ending in `.rlink` distinguishes the link-only invocation. Some long argv arrays have an omitted tail in strace, including the literal flag. The original flag-only classifier is retained for audit. Every selected command includes its original recorded line digest and raw trace digest.

## Separate scope controls

- Moving a native tracked function 256 columns changed the fixed mixed-library public hash. In metadata-only output the established eight-bit column collision was preserved. The tracked-function, private-method and public macro controls all retained their original prefix hit pattern. Native outputs reported the shifted columns.
- Independently of the public hash, a warm, fully recompiled reader of a tracked function pointer can still print 1 instead of 257. The two emitted producer files, `.rmeta` and `.rlib`, were byte-identical between that warm run and the run that cleared only the reader’s incremental directory. Clearing the reader produced 257. Direct ordinary upstream stable Rust 1.99.1 reproduced the same result with no Ohm features, on both rlib and mixed rlib/cdylib. Matched and released Ohm also reproduced it. Stock Cargo’s ordinary Ohm defaults launch a full reader on this test. Explicit incremental opt-outs have separate recorded results.
- For metadata-only RDR, explicitly applying `-Zincremental-ignore-spans` only to the producer can still panic a warm span-sensitive reader. Applying it to both, using neither flag, or compiling without RDR on both succeeds in this test. The ordinary configurations were also checked on released Ohm, both matched arms, and upstream Rust. This optional heterogeneous configuration is outside the default-mode fix tested above.

## Data files

`matrix.json.gz` contains 22 three-phase workspace cases for each main compiler, the upstream baseline, actual Rust invocations and exit statuses, typed producer hashes, runtime outputs and ELF hashes, stderr, the four run-make results, and their raw-file digests. `scope.json.gz` contains separate direct replays, actual argv, library and executable identities, prefix controls, pre-fix intermediate and explicit profiles. Within that file `fixed` denotes the earlier table-only negative control and `fixed2` denotes the final fix. In the other files `fixed` is the final fix unless the label explicitly reads `fixed2`. `ordinary.json.gz` reports the same explicit producer-only setting without RDR. `ruff.json.gz` has complete typed name, kind and freshness rosters, selected successful native execs and their original line digests, both producer public hashes, native outputs and CLI diagnostics. Paths in published text use stable aliases. Tokens used as hashes refer to retained original bytes.
