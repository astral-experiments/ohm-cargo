# Cargo skips reading relink inputs when there is no consumer

An ordinary incremental build after a real Ruff `TextSize` edit produced the same executable with each Cargo. The candidate still opened all nine object files and the link recipe, checked that they were regular files, and checked the executable’s metadata. It avoided reading 43,317 bytes and writing a 3,486-byte manifest. The unchanged repeat ran zero compilers and linkers in both arms.

| Cargo I/O on the genuine edit | Parent with incremental compilation | Candidate | Parent without incremental compilation | Candidate |
| --- | ---: | ---: | ---: | ---: |
| Object payload read | 29,128 B across 9 files | 0 B | 13,192 B across 2 files | 0 B |
| Link recipe read | 14,189 B | 0 B | 11,119 B | 0 B |
| Optional manifest written | 3,486 B | 0 B | 1,249 B | 0 B |
| Read-only object and recipe opens | 10 | 10 | 3 | 3 |

The candidate attempts to remove any old or reintroduced manifest before and after compilation. Both unlinks returned `ENOENT` on these dirty candidate builds. The omitted payload reads can no longer surface device errors that occur only during a read. Omitting the optional manifest also removes its publication-time errors. Both Cargos continued to report invalid inputs, missing executables with saved objects present, and a directory replacing the manifest.

## Workload and controls

The fixture copies the six files from Ruff’s `ruff_text_size/src` before and after the addition of `TextSize::saturating_sub`. An unchanged caller initially resolves the method to its trait fallback and prints 71 on underflow. After the edit, the inherent method gives 0. Both Cargo arms compiled the library and its caller and performed the same stock native link in each dirty phase. All full executable SHA-256s matched between arms for each phase and compilation mode. The fixture uses small local manifests with default library features. The before and after sources and their digests are included. [Ruff change](https://github.com/astral-sh/ruff/commit/438ef334d3e71ef0ac70927c799fb159d8f25267)

| Admitted commands across both Cargos | Count | What was checked |
| --- | ---: | --- |
| Historical build syscall captures | 16 | Original, unchanged, edited and edited-unchanged, with and without incremental compilation. |
| Independent native command captures | 16 | Actual compiler, GCC, collect2 and Wild arguments and the temporary inputs observed at Wild entry. |
| Output validation and wrapper controls | 36 | Bitcode cleanup, executable checks, unusable object/recipe paths, zero-object success, stray records, retry and explicit opt-out. |
| Compiler reports and explicit cached relinking | 26 | Empty and named reports, withheld notification with an authentic stale report reinserted, a genuine next retrain, explicit bin and integration links. |

A successful compiler followed by the wrapper deleting its new internal executable left the old public program at 17. With saved objects present, both Cargos failed the command. When the wrapper removed every object as well, both retained the existing permissive preparation behavior. Both also rejected symlink and FIFO objects or recipes, an unreadable object, a missing recipe, and a directory occupying a bitcode path. Ordinary bitcode cleanup succeeded.

Both Cargos retained genuine empty and named unused-extern reports. The interference control removed only the new compiler notification and installed the exact previous named manifest after precompile invalidation. The parent overwrote it with a record carrying no proof, and the candidate removed it. Both subsequently accepted a genuine report. With cached codegen explicitly enabled, a Rust library’s private edit and the changed public API of an unused integration-test dependency each produced one full compiler, one link-only compiler and one real stock Wild. Their native programs passed. The eight public replay-driver smoke commands are recorded separately.

## Interpreting the argument and syscall records

Full `rustc` argv hashes matched across arms. In nonincremental builds, the only unequal native arguments were the compiler-created temporary filenames. Rust’s symbols object had identical contents, its raw-dylib directory was empty, and GCC’s resolution file was empty. The GCC, collect2 and Wild vectors preserve all arguments in order and identify the temporary roles by their actual parent directory and flag.

Two independent incremental compilations chose different CGU filename suffixes for all 12 cold objects and all nine edited objects. Each changed name occupied the same argument position and had the same CGU stem, file size and full payload SHA-256. The ledger retains both literal relative names. The verifier requires byte-for-byte equality of every other persistent argument.

`commands.json.gz` contains the Cargo artifact and build-finished messages needed for each verdict, the raw stdout/stderr/result commitments, original per-thread syscall hashes and lengths, and selected decoded syscall arguments/results with original line hashes. It also contains full native argument vectors with the private root paths replaced by `<WORK>`, `<SDK>` and `<RUST>`. Both the original raw argv hash and the logical-vector hash are preserved. File payload buffers, machine-private path prefixes and unrelated trace lines remain in the private original. The public verifier re-aggregates read, write and open counts from the decoded events, compares native arguments and original object hashes, and checks all required controls.

`subjects.json` binds the parent `5394ce8817` and candidate `b29c836708`, their source trees, built Cargo executables, compiler, driver, Wild, PGO profile, build receipts and the input archive digest for each section. Both release builds had 239 ordered externs and 335 link inputs including 326 rlibs. `change.patch` contains the exact source change. One preliminary acquisition stopped after a successful compiler because its reader treated a Cargo diagnostic as an artifact. Its exception, raw digests, real process events and zero admitted cases are in `subjects.json`. The completed supplementary passes are separately identified there.

This component measures filesystem operations. It contains no scored instruction or wall-clock samples. The separate preregistration defines the larger Ruff workload, order and decision criteria. [Prospective instruction and wall-time study](https://github.com/astral-sh/ohm-cargo/tree/cbbd64db83ce4bb43ba5f00a84ed6008c7c20c44/benchmarks/ruff-dev-loop-20261027/rc19-ty-server-proofless-hashing-plan)

## Verify and reproduce

Run the portable verifier with Python 3.11 or later.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
```

To exercise the edit with either enrolled SDK, use an ordinary Linux x86-64 account, rustup, GCC and an unused path. The command verifies all four tool hashes, creates a private rustup alias and separate Cargo target/build directories, runs the two source revisions, invokes the real executable four times and records the results. Each invocation uses `cargo +ohm`.

```sh
python3 -IB reproduce.py /path/to/enrolled/sdk /path/to/new/private-run
```
