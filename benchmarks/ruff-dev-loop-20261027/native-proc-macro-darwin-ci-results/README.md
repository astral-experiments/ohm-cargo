# Native proc-macro invalidation on Apple Silicon

The checked-in Rust source for the reader and proc macro stayed fixed. A C function linked into the macro changed from returning 17 to 29. Both the derive and attribute expanded their return value into the executable. Each command invoked a new compiler process with an explicit `-Zcache-proc-macros`. The edit, unchanged repeat and restoration reused the original incremental directory. Each independent comparison started with its own empty directory.

| Darwin arm64 reader | Original | Edited | Unchanged repeat | Edited empty | Restored | Restored empty |
| --- | --- | --- | --- | --- | --- | --- |
| Official Ohm 1.99.0-17 | 17,17 | 17,17 | 17,17 | 29,29 | 17,17 | 17,17 |
| #246 compiler source, stage 1 | 17,17 | 29,29 | 29,29 | 29,29 | 17,17 | 17,17 |

Each pair lists the derive value first and the attribute value second. On both compilers, the only changed nonempty file-backed Mach-O section payload we hashed in the proc-macro dylib was `__TEXT,__text`. Restore returned that section to its original digest. Load commands, signatures and other bytes outside the extracted sections are covered by the separately recorded whole-file SHA-256.

The source-matched compiler also ran the checked-in run-make case on macOS, with its Linux selector changed to macOS in the temporary CI checkout. Compiletest used terse reporting, with one pass, zero failures and zero ignored. The workflow command and its CASE environment value identify the selected fixture. The two changed Git paths on the private QA branch contain the CI workflow and the auxiliary reader script. The candidate uses #246’s exact compiler tree and Cargo gitlink. It is a stage-1 CI build. The comparison arm is the SHA-verified distributed Apple Silicon -17 package. [CI run](https://github.com/astral-sh/ohm-rust/actions/runs/40730837103)

Run `sha256sum -c SHA256SUMS` and `python3 verify-packet.py` in this directory. The original Actions ZIP retains every captured process argv, status, stdout, stderr, and the native image digests. The selected CI log lines retain their original line numbers and byte digests. The complete CI job log is available from the linked run.
