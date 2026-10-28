# Incremental consumers of cross-crate source locations

On the published Linux Ohm 1.99.0-17 compiler, a native function pointer to a `#[track_caller]` function returned column 1 after its definition moved to column 257. Rebuilding the same source with an empty incremental directory returned 257. An independent case moved an identifier 11 columns in a producer compiled with `-Zincremental-ignore-spans`. Its warm reader panicked twice in `module_children`. A clean reader succeeded.

| Compiler | Commands | Panics across the four metadata configurations | Incorrect native columns | Checked-in regression |
| --- | ---: | ---: | ---: | --- |
| Published 1.99.0-17 | 141 | 8 | 12 | Failed |
| Rust #243 | 141 | 8 | 12 | Failed |
| First full-column candidate | 141 | 0 | 0 | Passed |
| Rust #245 with #244 | 141 | 0 | 0 | Passed |

Each arm had its own incremental directories and ran at the same logical compiler and workspace paths. The experiment covered both ordinary and public-API-hash metadata, rlib and mixed rlib/cdylib native builds, retained readers, empty readers and movements of 255, 256, 511 and 512 columns. The counts include repeated invocations of the two reproducers. The final Linux compiler was built with the retained release PGO and BOLT inputs. Its compiler tree is identical to the one in the candidate Cargo pin. Corroborating platform CI and the full Ruff build are tracked separately. [Compiler change](https://github.com/astral-sh/ohm-rust/pull/245) · [Candidate Cargo pin](https://github.com/astral-sh/ohm-rust/pull/246)

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py`. Add `--rust-git /path/to/ohm-rust` to check the compiler trees and the three regression source files against Git. The archive includes all 564 command records, their 1,128 stdout and stderr streams, the executable and compiler hashes, source fixtures and the launcher. No timing claims are derived from these runs.
