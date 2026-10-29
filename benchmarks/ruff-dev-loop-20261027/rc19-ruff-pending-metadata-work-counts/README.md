# Ruff metadata generation after a real manifest edit

Ruff changed its Cargo test and doctest settings in 27 packages at `2d6ce561250a464e1fa231ef30e54d0f029f76a4`. Both complete 30-file transitions use the original Git bytes and the same lockfile. The historical 47-member command was `cargo +ohm check --workspace --locked --offline -j8 --message-format=json`. [Original subject](https://github.com/astral-sh/ohm-cargo/tree/d0325acfadb4c8e38ee5a669f665d58c20f13c88/benchmarks/ruff-dev-loop-20261027/rc19-ruff-multi-select-subject)

Ordinary Cargo with no process or filesystem tracing reproduced the stale edge in both directions. Four additional edits observed using inotify reproduced it four times. The target paths came from Cargo’s typed output, the actual rustc output directory and the consumer’s literal `--extern ruff_python_ast` argument. Both metadata files retained the same complete bytes and the same inodes through all six edits, while their final mtimes diverged. The next check called `ruff_python_ast` newer than `ruff_python_index`. It rebuilt the index, then accepted it on the second repeat. Full syscall tracing changed the schedule in both directions. In that series the two files finished with equal generations and the extra index check disappeared. Inotify timestamps describe delivery to the observer and some notifications can coalesce. [Forced publication-order control](https://github.com/astral-sh/ohm-cargo/tree/0f4c483b2dd7375495c8018a5b5ff2089b73470c/benchmarks/ruff-dev-loop-20261027/rc19-rmeta-publication-order-parent-results)

| Actual full rustc invocations | Original Cargo | Pending-dependency candidate |
| --- | ---: | ---: |
| Restore parent manifests | 51 | 56 |
| First unchanged parent check | 24 | 1 |
| Second unchanged parent check | 1 | 1 |
| Reapply committed manifests | 51 | 56 |
| First unchanged committed check | 12 | 1 |
| Second unchanged committed check | 1 | 1 |

Every edited command linked the `ruff_macros` shared library with authenticated stock Wild. Each settled check compiled `ty_python_semantic` due to the separate foreign-span fallback. The candidate added the same five full edit-time jobs in each direction. They were `ty`, `ty_completion_bench`, `ty_completion_eval`, `ruff_benchmark` and `ruff_dev`. Cargo selected the same 510 typed actions in the two arms. The baseline is the release-PGO Cargo built from `235f9228651b74c591e6f62cae4c9b761448dd2d`. The candidate is a debug Cargo built from `b3360c5eda186845b9a2ba6e5330a97c07d4acf2`. Both used the actual published -18 rustc and Wild. The first use of the candidate selected its own cold cache namespace, succeeded and performed 510 dirty units. That cold setup is excluded. Each admitted arm had a separate warmed baseline and two unchanged controls. These data have no matched wall-time comparison. [Matched timing protocol](https://github.com/astral-sh/ohm-cargo/tree/4705bd922e3587ed786645d013b8bd9966381123/benchmarks/ruff-dev-loop-20261027/rc19-pending-metadata-clock-plan)

A separate private edit reduced the visibility of `Token::is_triple_quoted_string` and also changed the consumer source. Both warm checks and the independent initially empty build failed with the same E0624 at line 50, column 22 of Ruff’s `multiline_ranges.rs`. Restoring the exact source passed in both arms, including an independently empty build for each. The following unchanged package check had zero dirty artifacts.

Run `sha256sum --strict -c SHA256SUMS && python3 -IB verify.py --mutations`. The packet contains normalized observations, the original log digests, the source projector and the verifier.
