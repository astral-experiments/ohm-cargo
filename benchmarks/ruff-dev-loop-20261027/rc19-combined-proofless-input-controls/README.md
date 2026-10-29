# Cargo relink-input controls on the combined safety branch

This comparison uses Cargo #284 as the parent and a local direct descendant that skips payload hashing when rustc supplies no unused-dependency report and Cargo cannot reuse cached codegen. Both include the five repairs for symlinked cache files. Their release-profile builds used the same compiler, training profile, 239 external crate inputs and 335 native linker inputs. [Parent safety patch](https://github.com/astral-sh/ohm-cargo/pull/284) · [Original mechanism experiment](https://github.com/astral-sh/ohm-cargo/tree/0b4d43a9a9c711cafdc80f900156bbd8bfcdbe8b/benchmarks/ruff-dev-loop-20261027/rc19-proofless-relink-inputs)

A historical Ruff `TextSize` edit changed an unchanged caller’s result from 71 to 0. Both Cargos rebuilt the same two crates, performed the native link, produced byte-identical executables per phase, and ran zero compilers and linkers on every settled repeat. The count below measures Cargo’s own reads after the native link. [Ruff source change](https://github.com/astral-sh/ruff/commit/438ef334d3e71ef0ac70927c799fb159d8f25267)

| Dirty build | Parent payload read | Candidate payload read | Optional manifest bytes saved | Object and recipe opens, each Cargo |
| --- | ---: | ---: | ---: | ---: |
| Incremental | 43,564 B | 0 B | 3,628 B | 10 |
| Nonincremental | 24,389 B | 0 B | 1,301 B | 3 |

The 94 commands cover the historical edit, independent native command captures, wrapper and filesystem errors, and the distinction between an absent compiler report and an explicit empty report. Missing executables with saved codegen objects, symlink and FIFO inputs, bitcode cleanup, and stray manifests were exercised. An explicit cached relink with current inputs still ran a real stock Wild. Skipping the optional reads and publication removes the errors that could previously arise from those operations. Wall time and retired instructions are separate measurements.

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py` here to verify the portable results. The packet includes normalized process and filesystem observations, whole-file hashes, and commitments to all eight raw capture archives. The full private raw verifier consumed 2,680 per-thread kernel streams. To repeat the four ordinary build phases with either enrolled Linux SDK, run `python3 -IB reproduce.py /path/to/sdk /path/to/new/private-directory`. Each standalone replay records the program’s stdout, freshness, and executable digest.
