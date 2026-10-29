# Ordinary Ruff linter builds on the second archive experiment machine

On Linux x86-64 EPYC Milan, the released Ohm 1.99.0-18 rebuilt ten of 248 Rust units after reversing Ruff's f-string change. The same ten libraries rebuilt when the source was restored. All 248 units were fresh on each immediate repeat. A separate edited build began with empty target and shared build directories at the same paths and rebuilt all 248 units. These six commands used the ordinary release compiler and linker. [Ruff edit](https://github.com/astral-sh/ruff/commit/1e9287d7654f1dbe4943d67ed5ac5363c9ee2161) · [Ohm release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-18)

| Source and state | Fresh / total | Linter rlib SHA-256 prefix | Caller ELF prefix | SIM222 lines |
| --- | ---: | --- | --- | --- |
| Original, warm | 248 / 248 | `503e3a4d` | `b538463b` | 1 |
| Apply historical reverse | 238 / 248 | `ed50cec8` | `b2c84a8a` | 2, 3, 4 |
| First unchanged edited build | 248 / 248 | `ed50cec8` | `b2c84a8a` | 2, 3, 4 |
| Independently empty edited build | 0 / 248 | `5a19ea98` | `72ee8430` | 2, 3, 4 |
| Restore original source | 238 / 248 | `aa1cd318` | `b538463b` | 1 |
| First unchanged restored build | 248 / 248 | `aa1cd318` | `b538463b` | 1 |

The selected command was `cargo +ohm build --locked --offline -j8 -p ruff_linter --message-format=json`. A separately compiled Rust program loaded the exact linter and AST libraries from each command's artifact messages and printed the SIM222 results for four Python lines. Warm and independently empty edited builds agreed on every diagnostic, although both their raw archives and caller binaries differed. Restoring the source recovered the original caller's entire executable. The restored linter archive had its own digest.

The original and edited warm linter archives were both 101,853,960 bytes. All 256 native objects matched at their exact previous offsets. Those object payloads accounted for 77,383,632 bytes. Comparing the two entire archives in aligned 64 KiB chunks found 101,067,528 equal bytes, including the final partial chunk. The held old inode stayed readable with its original digest across the real edit. Cargo gave the selected library a separate top-level hard link. These observations establish a potential source of bytes for an in-process writer on a clone-capable filesystem.

The registered two-machine comparison of the preload prototype stopped before any timed triplets. On the Genoa host Cargo moved 185 of the 248 artifact rows into its worktree cache, changing both the workload and the archive geometry. This Milan packet contains only stock controls. No ordinary Cargo speedup has been measured for this candidate. [Registered protocol](https://github.com/astral-sh/ohm-cargo/tree/cd2dee0bcc68a304cf7c0c68ddd82db7e3828e2a/benchmarks/ruff-dev-loop-20261027/rc19-rlib-package-plan) · [Genoa routing and native controls](https://github.com/astral-sh/ohm-cargo/tree/6f633f4d30e27aad6106768e1cad0dc0ffb54f07/benchmarks/ruff-dev-loop-20261027/rc19-rlib-package-hloader-native)

Run `python3 -IB verify.py` and `sha256sum --quiet -c SHA256SUMS`. The projection records complete artifact and executable hashes, all dirty target names, terminal consumer outputs and commitments to the original Cargo message streams. `collect-package-stock.py` can regenerate it from the archived six-command result directory. The compiler input and actual consumer program are included.
