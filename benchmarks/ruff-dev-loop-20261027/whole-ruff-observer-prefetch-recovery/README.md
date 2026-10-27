# Retraining a missing Ron observer record on Ruff

After the 16-pair per-command whole-workspace comparison, we removed the active encoded `ron` observer record from one private copy of V's trained test target. V is the FIFO-safe Cargo control at `d38fdd02503662de04c52f5f370f5dd81bddf868` with production PGO binary SHA-256 `dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1`. The initial copy matched the primary control's roster, both observer records, real Ruff diagnostics, and all 110 raw ELF outputs. The original qualified target and shared store retained their original directory inodes. This supplement ran after all timing and audits, using the same pinned Ruff, Cargo settings, compiler, logical paths and exclusive measurement lock. [Primary data and qualification rules](https://github.com/astral-sh/ohm-cargo/tree/0c2aec0c36136aa7cfb05785d525c1caf3c2c0b4/benchmarks/ruff-dev-loop-20261027/whole-ruff-observer-prefetch-results)

| `cargo test --no-run` after removal | Dirty Cargo units | Full rustc | Link-only rustc | Native linker runs | Active record complete |
| --- | ---: | ---: | ---: | ---: | --- |
| First invocation | 56 | 1 | 50 | 50 | No |
| Second invocation | 56 | 1 | 50 | 50 | Yes |
| Third invocation | 0 | 0 | 0 | 0 | Yes |

The full compilation on the first and second invocations was `ron`. The regenerated encoded record and its rustc `.d` exactly matched their pre-removal bytes. The other namespace’s passive record retained its bytes and filesystem identity through all three invocations. The final anchor reported all 619 units fresh, the same 102 runnable targets and the same diagnostics as the original. The first command which removed the record operated only on the copied V directory. The comparison ended before C was created.

The original post-score auxiliary attempt stopped when its rustc executable-open calibration observed two opens. The subsequent unscored supplement passed the single-open calibration and then failed its strict raw-equality gate after retraining. Of 110 ELF outputs, 107 matched the primary raw SHA-256. Exactly 33 bytes differed in each of the other three tests. Thirty-two held the GNU build ID and one held the `.rodata` section header’s `sh_entsize`. In original-to-recovered order, that field changed from 0 to 8 in `visitor`, 1 to 0 in `fixtures`, and 8 to 0 in `e2e`. The registered comparison of bytes outside those two fields matched for each file. Both SHA-256s, every precise byte edit and the offset of the changed header are retained. The raw-equality failure and its exit code of 1 are preserved. Neither auxiliary attempt contributed timing observations.

Run the following from this directory. It checks this archive, replays the step and ELF comparisons and verifies all 99 changed bytes against the decoded ELF fields. The optional `--original-target /path/to/original/target` also applies the saved byte patches to the three original files in memory and verifies the resulting SHA-256s. Access to the private repository is required for the primary study.

```sh
sha256sum -c SHA256SUMS
python3 -B verify.py
```
