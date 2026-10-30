# Reusing saved codegen for native rechecks in Ruff

On Linux x86-64 we ran the same complete Ruff workspace test build on Cargo #291 and #292 with a common Rust driver, Wild, 498 locked archives, four CPUs and independently empty target and shared directories. We then ran two ordinary unchanged commands on each install. The fifty tracked targets were enumerated before acquiring data. This study counts processes and validates products. It has no elapsed-time or instruction endpoint.

| Cargo | Visit | Typed artifacts | Fresh | Full rustc | Link-only rustc | Real Wild | Tracked links |
|---|---|---:|---:|---:|---:|---:|---:|
| #291 | Empty | 619 | 0 | 623 | 0 | 188 | 50 |
| #292 | Empty | 619 | 0 | 623 | 0 | 188 | 50 |
| #291 | Each unchanged | 619 | 470 | 107 | 0 | 103 | 50 |
| #292 | Each unchanged | 619 | 470 | 91 | 16 | 103 | 50 |

The 16 reused compilations were five library test harnesses (Unicode names generator, notebook, formatter, Python trivia and source file), five `ruff_text_size` tests, five `ruff_annotate_snippets` tests and `ruff_cache`'s `cache_key` test. The actual terminal `ty_server:e2e` and `generate_inline_tests` still used full rustc. Real native link count was identical.

The Linux kernel trace has 74,726 per-thread files. The observations preserve the multiplicity, role and complete original argv digest for every enrolled rustc and Wild. #292 used the literal two tokens `-Z link-only` and one saved `.rlink` input on each cached compilation. Readback found all 16 distinct recipes, their file headers and bodies. The joined-token-only original display undercounted these jobs. The separate role rule was frozen during the candidate's cold build, before its first unchanged command. Seventeen cold non-native helper execs used relative names. The full trace join handles precisely that recorded representation and retains its earlier rejection. Each enrolled compiler and linker had an absolute executable path.

All 50 full executables and their complete test listings matched across Cargo versions at each corresponding visit. Among histories within either version, one `ty_python_semantic` executable differed between cold and unchanged. Its only differing allocated section was the GNU build ID. Its code, read-only data, program headers and loadable segments after excluding that note matched. The original and warm hashes are retained. The full `ty_server:e2e` listing contained 200 tests in all six visits. We ran its inlay-hints case and two notebook cases in every visit. All 18 passed. The packet supplies complete libtest stdout and the byte length and SHA-256 of original test stderr; verbose LSP debug output contains machine-specific paths. A separate protocol covers historical edits, errors and native library replacement.

```sh
python3 -IB verify-extra.py --self-test
python3 -IB rerun.py --help
```

For an independent Linux x86-64 run, use Python 3.11+, Git, rustup with Cargo and rustc proxies, strace, zstd, four available cores, at least 43 GiB free on the chosen filesystem and at least 12 GiB available RAM. The registered host used higher entry reserves (120 GiB disk and 48 GiB available RAM), a stock system GCC and an Ohm-built SDK. Provide two Cargo executables built at the commits below with the `ohm-defaults` feature and their source revision in `cargo -Vv`, one complete SDK containing rustc, matching std and its unchanged Wild, and a Cargo registry directory with the locked sources, sparse index and archives. The local command accepts an existing Ruff Git clone and an absent scratch path. Substitute four CPU numbers available to the current user. Preserve the filesystem floor and avoid other compilers while comparing.

```sh
python3 -IB rerun.py \
  --ruff "$RUFF_CHECKOUT" --registry "$CARGO_REGISTRY" --sdk "$OHM_SDK" \
  --control "$CARGO_291" --candidate "$CARGO_292" \
  --work "$SCRATCH/ruff-codegen-recheck" --cpus 0,1,2,3
```

The qualified command was `cargo +ohm test --workspace --no-run --locked --offline -j4 --message-format=json`. It used private mount namespaces at one stable path. The portable launcher offers the same ordinary commands at stable literal paths, saves raw results and verifies its inputs. Its CLI and classifier were tested. The six complete observations above came from the source-bound mount controller. Matching source-built development Cargo executables and a stage1 compiler were used. These are separate from signed release binaries.

Sources are [Cargo #291](https://github.com/astral-sh/ohm-cargo/commit/84af87848a5a952ba61ae6a2cc5b22da24130200), [Cargo #292](https://github.com/astral-sh/ohm-cargo/commit/98d431a99779ccfbcfe42dfa74dd541de3a92d05), [Rust](https://github.com/astral-sh/ohm-rust/commit/ad005f99d0b51fd62b5c237bc13b31b371a1686e) and [Ruff](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001). The pinned Ruff license is included.

