# Ruff's ty_server end-to-end executable after the Cargo cached-codegen fallback

This unscored Linux x86-64 correctness study selects `cargo +ohm test --locked --offline --no-run -j4 -p ty_server --test e2e --message-format=json`. A separate execution of each successful published harness prints the full inventory and runs the two notebook tests about a range past the end of a cell. A separately compiled Rust caller observes whether the real parser accepts `from x import (*)`. The notebook tests establish basic behavior of the selected binary while the parser caller distinguishes the two source states.

The base is Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. Reversing the nine inserted parser lines and one corresponding Python input from Ruff `a50dc58628691ee00a21809e19bdea71958e4f3c` also removes the matching current snapshot. The historical and current snapshot bytes differ because the pinned checkout already includes a separate diagnostic snapshot update. Actual input path hashes are retained for all three files. The invalid control adds a deliberate `u8`/string mismatch to that edited parser file. [Ruff #26021](https://github.com/astral-sh/ruff/commit/a50dc58628691ee00a21809e19bdea71958e4f3c)

The compiler is optimized stage1 Rust `ca780121cea38bb9b0538d020d4bcce76ca30cbc` with its 53 matching target-library files, and the normal Rustup-selected Cargo and stock Wild linker. Each arm uses a private copy of the same 498-archive offline registry. Each warm-up or empty control starts with independent, empty target and shared directories at identical absolute paths. The earlier 2.6 GiB target was copied and independently checked against its published executable hash. It was kept as a separate reference. Every participating Cargo command ran on cores 8–11 without a compiler wrapper. All paths and build output directories belonged to this study.

Read and verify the per-command results with `python3 -IB verify.py`. The data contains all successfully executed compiler and linker argument digests, each selected binary's complete hash and ELF section hashes, every typed target name/feature/output, the exact harness inventory, two executed notebook outcomes, and the external parser result. The raw exit and source receipts bind the unmodified command streams and system-call logs held by the custodian. The included prior report identifies the earlier 300-unit experiment without substituting its binaries or outcomes for any new command.

The reported Cargo images and compiler configuration are listed in `subjects.json` and the per-arm enrollment. Default behavior is tested. The deliberately experimental explicit `-Zrelink-only=yes` opt-in falls outside this study.

## Recorded results

| Arm | Historical edit, full rustc | Historical edit, cached rustc | Stock e2e links | Warm and clean edited ELF | Original and restored ELF |
|---|---|---|---:|---|---|
| pgo-final-B | e2e, ruff_python_parser | 0 | 1 | Exact | Exact |

All successful commands produced the same ordered inventory of 200 tests. Each selected executable passed both notebook tests outside Cargo. Every settled warm repeat had 300 fresh units and produced no native compiler or linker process. The invalid control returned Cargo 101 with E0308. The independent empty invalid control and the prior warm failure are recorded separately.

The custodian can run `python3 -IB verify.py --private-root ROOT` to rehash the stored full binaries, their executable code sections, raw Rust and native tool executions, Cargo JSON streams, and the parser caller outputs.

The H4 production PGO build of Cargo `a8f0c9aa0` completed on the recorded 239 ordered externs and 335 native linker operands, including 326 rlibs. All nine commands executed that same Cargo with optimized stage1 Rust. The independently checked 16-command debug comparison is bound separately by its manifest. This study records native correctness and command counts.
