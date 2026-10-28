# The published ohm-1.99.0-17 Linux package with a spaced SDK path

The full end-to-end validation used the official x86-64 Linux archive with SHA-256 `163267d26889b1bd2c467d7db97efee42cd2ac9dc9af2abc3a56ade8da9a9572`. The release installer registered the toolchain under a fresh private rustup home. The effective sysroot ended in `Ohm SDK` and the existing global alias retained its inode, link target and timestamps. [Release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-17) · [Packaging run](https://github.com/astral-sh/ohm/actions/runs/40609224340).

Cargo was `a0c7d08c898d3fdff992f2f431dec57d2486add2` and rustc was `bfa236f639034f61ec884c15bd1f4e0b75e508ac`. The installed executable SHA-256 digests were `4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3` for Cargo, `7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c` for the rustc frontend, `618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7` for the driver and `0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5` for Wild. The verified provenance, published manifest, asset IDs and checksums are in the packet.

## Native correctness

A workspace using `include_bytes!` began at 17. Replacing the real input with a four-byte value of the same length and restoring its nanosecond modification time produced 29. A neighboring path contained a literal backslash and space and already held the future bytes. The ordinary unchanged build and check were fresh. The changed check produced E0308 with the same complete JSON error as its independent empty target.

Two further cases reversed the declaration order of external libraries with different physical path bytes that display identically. Both reported E0308 on the backdated edit. The reader rebuilt on each ambiguous unchanged state. An unambiguous literal replacement-character filename reached a fresh repeat and still detected the edit. The results include all five terminal Cargo states for each case.

## Ruff test compilation

The Ruff worktree was clean at `93526150df078af7dd8fc4226cdcc469539d2001`. Each phase used `cargo +ohm test --no-run --workspace --locked --offline -j4 --message-format=json`, with default trust and 498 verified offline registry archives. Actual compiler and linker processes were classified from successful native execs and the installed binary identities. No test bodies ran. Separately executed listings registered 200 ty_server integration tests and four ruff_python_stdlib tests on every phase.

| Phase | Fresh / 619 | Full rustc | Link-only rustc | Wild | System linker | Same raw native files as preceding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 0 | 636 | 0 | 201 | 62 | — |
| Unchanged 1 | 563 | 1 | 50 | 50 | 0 | 110 |
| Unchanged 2 | 619 | 0 | 0 | 0 | 0 | 110 |
| Unchanged 3 | 619 | 0 | 0 | 0 | 0 | 110 |

The initial native collection stopped after the genuine cold command because the validator incorrectly expected format 4 in its incomplete record with no checksums. The shipped Cargo writes format 2 in this case, then format 4 when it acquires checksums. The first failed assertion, preceding artifacts, and source rule are bound in the packet. The validator rehashed all original cold outputs and native traces before running the unchanged commands. The original cold command was executed once.

All phases produced 110 tracked native files, 102 Cargo-reported executables, 84 test-profile executables and 18 ordinary executables. The sealed observations include every native product hash, the 619 Cargo rows, actual native process roles and per-process trace file commitments. Registry source packages and compiler traces remain separately hash-addressed on the originating host. These traced correctness runs collected no scored wall times.

The native runner manifest has SHA-256 `c1f79668d24573e7b1da7f8e11b2ad83dff6a9dba08e30da6b53b451b58e387e`. Run `python3 verify.py` for an offline check. Run `python3 reproducer/ordinary-reproduce.py --toolchain ohm` and `python3 reproducer/unicode/reproduce.py /tmp/new-empty-ohm-case` on an installed Linux release for the independent small controls.
