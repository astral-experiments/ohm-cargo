# Synchronized input changes with the pending-metadata Cargo pair

Both Cargo executables used the published Ohm 1.99.0-18 Linux x86-64 rustc, driver and Wild. Across two arms, 52 independently initialized histories ran 280 ordinary Cargo commands. Every command's outcome, program sample, caller freshness disposition and structured error agreed across the two arms.

| Input changed after the consumer observed 17 | Interrupted command | Two unchanged commands | Independently empty command |
| --- | --- | --- | --- |
| Tracked macro file, Rust include_str!, binary include_bytes!, or C-backed proc-macro DSO | Program printed 17 | Both printed 29 | Printed 29 |
| Same-source C-backed DSO, requiring u16 when its new token is i16 | Check passed | Both reported E0308 | Reported E0308 |
| Standalone Rust metadata with its exported token moved 256 columns | Compiler refused the colliding StableCrateId | Both reported E0308 | Reported E0308 |
| Conventional DSO definition or metadata with a changed Rust definition | Compiler refused the colliding StableCrateId | DSO programs printed 29, metadata checks reported E0308 | Same program output or diagnostic |

The file readers, C-backed executable and standalone metadata cases each covered an initially empty reader and a previously trained reader with a real source edit. The additional typed DSO covered the trained history. The conventional Rust-identity controls covered the first compiler. Each case ran with a current mtime and with the original nanosecond mtime preserved. After replacement, every warm build or check invoked the real compiler for the affected caller.

We reopened 72 final executable artifacts. Every program printed 29, and each warm program's entire stdout matched its independently empty counterpart. Each of the 48 E0308 results matched its clean structured error, including source coordinates and labels. Three further executable reads retained representative stdout bytes. The ledger contains all 13 distinct complete terminal stdout values and seven diagnostic shapes.

The original -17 standalone-metadata experiment preserved private and public crate hashes when the token moved. In the -18 controls, rustc's metadata inspection showed identical stable crate IDs but different private and public hashes. The interrupted compiler gave a collision diagnostic. This explains four end-of-run rejections from the trained metadata driver, whose final guard required a successful initiating Cargo artifact. All seven command rows in each history remain in the ledger. The newer released compiler includes the previously omitted source locations in the hash. [Released compiler change](https://github.com/astral-sh/ohm-rust/commit/35677e3e6764de18ca37d7ab5ed634dafea53876)

The independently typed DSO exercises a successful interrupted check followed by an invalid new type. The C implementation changes its return value. The Rust source, the ELF's serialized Rust metadata and its dynamic symbol table remain byte-identical while its executable code changes. The experiment verified rustc's existing executable mapping of the old inode before publishing the new file. All four copies passed the interrupted check and rejected the new signed type on both warm commands and from empty.

The shipped -17 Cargo kept reporting 17 on trained histories with the three file readers. The historical evidence verifiers were rerun before this study. The present arms are control Cargo 3a94265b… and candidate 51eb6c59… with the same released compiler. [Shipped -17 file results](https://github.com/astral-sh/ohm-cargo/tree/55fc99a09e3bb529294de08dd73f372abae22dd3/benchmarks/ruff-dev-loop-20261027/noquery-established-observer-results) · [Synchronized binary protocol](https://github.com/astral-sh/ohm-cargo/tree/d94e602e0f3b0eb357e9a386e3fc27971727937b/benchmarks/ruff-dev-loop-20261027/synchronized-compiler-inputs) · [Fixed-Cargo readers used here](https://github.com/astral-sh/ohm-cargo/tree/e41b8d460f8f2607e572587c01ec56708bb2ddb4/benchmarks/ruff-dev-loop-20261027/cargo-binary-input-mitigation)

Run the portable verification from this directory.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
```

To exercise the held-out typed check with a chosen toolchain, use the included source and a new private work directory. The other drivers are available at their exact public revisions in protocols.json.

```sh
python3 -IB typed-dso.py --root /path/to/new-private-root --sdk /path/to/chosen-sdk
```

The coordinator retains the full raw Cargo events, stderr, physical exec traces, dep-info, sources and native targets separately. The two main runners ended nonzero after recording their two expected historical assertion rejections each. Their other fixtures continued. An earlier setup guard stopped before any Cargo execution because it expected the sandbox filesystem owner to equal the ordinary host owner. All 280 commands used the ordinary user and a root-owned filesystem root.
