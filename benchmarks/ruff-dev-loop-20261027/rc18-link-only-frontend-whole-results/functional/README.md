# Released Rust frontend thread qualification on Ruff

Ten ordinary `cargo +ohm test --workspace --no-run --locked --offline -j8 --message-format=json` commands used the released Linux x86_64 Ohm -18 compiler, GCC, collect2 and stock Wild. Two independently empty workspace stores held the same Ruff source and tool paths. A used Cargo commit `7caf39914da1e28a67744ecbc963a5f26361474d`. B used commit `c9c7fb9df6ca7e8f0c9c12f2471a0d8663bf5c19`. An earlier candidate retained eight threads in the independent small native control and did not enter this workspace comparison.

The control built the original source from empty. The candidate built the historical notebook edit from empty. Both then exercised the edit, restoration and an unchanged command. Each command returned all 619 matching Cargo unit records. The two real notebook tests passed on the original source, failed on edited source and passed after restoration. Every run listed the same 200 tests. The edited and original whole e2e executable hashes matched the respective independent clean release builds.

| Matched command | Full rustc | Link-only rustc | Stock Wild | Byte-identical linked outputs |
| --- | ---: | ---: | ---: | ---: |
| Notebook edit | 12 | 43 | 52 | 52 of 52 |
| Restoration | 12 | 43 | 52 | 50 of 52 |
| Unchanged | 1 | 50 | 50 | 50 of 50 |

Every matched full rustc had the same complete arguments. On every matched link-only rustc, the sole argument change was the automatic frontend thread count from eight to one. Both unchanged commands still compiled `ron` and ran all 50 genuine native links. Each cold command also ran 52 unsuccessful GCC or collect2 version/configuration probes. All producing rustc and stock Wild invocations succeeded.

Two restored files differed in their GNU build ID and the `.rodata` section header’s `sh_entsize`. The 31,306,328-byte `fixtures-cfa340005b9ad559` changed from one to zero. The 21,242,488-byte `ruff_python_semantic-06b9ad6d035c77d0` changed from zero to eight. The verifier hashed all other ELF bytes before advancing either source state. Both physical versions of each differing file were subsequently superseded. The original four raw hashes, four build IDs and two complete-file masked hashes are recorded in `elf-fields.json.gz`.

`python3 -IB verify.py` checks the manifest, decoded packet, process ledger, typed unit inventory, Rust arguments, test outcomes, independent clean hashes and native ELF comparisons. It also verifies that the ELF-field reader rejects a changed text byte. The packet retains an original digest for each complete NUL-delimited argv and each original Cargo stream. External pathnames in the process projection are represented by digest. The process table covers 5,428 executable entries for the identified tool images. These functional checks contain no workspace wall-time measurements.

The raw gate records an earlier discarded 65-unit cold attempt. A concurrent mount replacement made its private target read-only and Cargo exited 101. A new empty workspace started after that operation finished. Its successful control cold command was reanalyzed from the original streams after the recording script classified cold configuration probes separately.
