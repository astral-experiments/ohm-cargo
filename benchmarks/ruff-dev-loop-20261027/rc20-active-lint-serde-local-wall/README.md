# Independent serde test-build timing on the released -18 compiler

The active-lint Cargo candidate saved 142.52 ms at the paired median over the first edit and its immediately unchanged test build. Across 32 pairs, the median relative reduction was +18.42% (95% interval [+17.88, +19.45]%) with 32/32 candidate wins and an exact two-sided sign-test p of 4.65661e-10. The parent was Cargo 97e5acfb7 and the candidate was 70baacdb3. Both used the same shipped -18 Rust and stock Wild on this host. [Prospective local plan](../rc20-active-lint-serde-local-plan/)

| Source direction | Phase | Parent / candidate median (ms) | Paired saving (ms, 95% CI) | Paired saving (%, 95% CI) | Faster |
| --- | --- | ---: | ---: | ---: | ---: |
| Both | Combined | 778.43 / 631.70 | +142.52 [+138.18, +151.48] | +18.42 [+17.88, +19.45] | 32/32 |
| Both | Edit | 703.80 / 559.24 | +140.47 [+138.42, +149.33] | +20.24 [+19.61, +21.24] | 32/32 |
| Both | Repeat | 73.56 / 72.90 | +0.88 [+0.10, +1.52] | +1.20 [+0.14, +2.06] | 23/32 |
| Reverse | Combined | 778.21 / 634.59 | +138.68 [+133.15, +143.90] | +17.80 [+17.02, +18.53] | 16/16 |
| Reverse | Edit | 705.51 / 562.14 | +138.43 [+133.81, +143.51] | +19.44 [+19.06, +20.30] | 16/16 |
| Reverse | Repeat | 73.69 / 73.04 | +0.42 [−1.57, +1.74] | +0.57 [−2.16, +2.34] | 11/16 |
| Restore | Combined | 778.43 / 627.75 | +150.34 [+140.24, +157.75] | +19.46 [+18.17, +20.41] | 16/16 |
| Restore | Edit | 703.22 / 554.77 | +148.11 [+140.13, +157.43] | +21.18 [+20.11, +22.65] | 16/16 |
| Restore | Repeat | 73.38 / 72.56 | +1.08 [+0.09, +2.12] | +1.48 [+0.12, +2.69] | 12/16 |

The primary combined endpoint passed. The protocol also requires each direction to demonstrate noninferiority of the standalone unchanged command separately. Its lower 95% paired saving must reach −3% and −5 ms in each direction.

Reverse repeat met both bounds. Its relative interval is [−2.16, +2.34]% and its absolute interval is [−1.57, +1.74] ms. The interval includes zero.

Restore repeat met both bounds. Its relative interval is [+0.12, +2.69]% and its absolute interval is [+0.09, +2.12] ms. The relative interval favors the candidate.

The primary and both directional unchanged bounds passed on this host.

The most adverse complete pair was 10 (restore, BA), at 768.74 ms parent and 655.95 ms candidate. All scheduled pairs are retained. Estimates use 20,000 within-direction/arm-order resamples. Each direction has eight AB and eight BA pairs. The earlier machine used the released -19 compiler, and its reversing-direction unchanged interval was [−38.62%, +1.60%]. The two hosts have separate estimates and intervals. [Earlier independent host](../rc20-active-workspace-lint-wall/)

## Work and correctness

Every command was an ordinary `cargo +ohm test -p ruff_text_size --features serde --test serde --no-run --locked --offline` on 93526150df. The only change reverses or restores three genuine workspace Clippy lint lines. The selected library and integration harness each received the actual `--allow=clippy::large_stack_arrays` only when that policy was present. The 553-package lockfile and all Rust sources stayed byte-identical. [Historical Ruff edit](https://github.com/astral-sh/ruff/commit/3edca130e22b2aba1d0cfe263e3f6a6679e166cc)

Four independent empty builds, one per image and source state, each ran 15 Rust compilers and six stock native links. All first source transitions ran two actual Ruff compilers and one stock Wild. The next unchanged invocation ran zero compilers and linkers. The traced reversions of an already visited state also did the required native work. The parent entered full workspace resolution on each first transition, while the candidate reused its cached resolution. Separately settling CARGO_LOG before that diagnostic preserved an identical environment across the transition. The wall commands used no tracer or logging.

Each measured arm received a genuinely empty private writable product/shared overlay over a donor trained only on that starting state. Source, registry, SDK and physical product paths at Cargo’s entry stayed fixed. Each sample checked the full test harness bytes, standalone metadata, strict ordered-object/archive witness and all three actual test results against both independent empty builds at the destination state. The archive witness allows only independently authenticated compiler-generated member-name variation and preserves raw archive digests.

After the last native flanks, 8 actual final/empty views were reopened read-only. All selected product files were copied and rehashed a second time. The archive contains 10 distinct complete product bodies (2,305,139 bytes). The private compressed raw ledger has SHA-256 `bce00d2fef482d7f4b43904c6e0812dcad4bde64e0f3f8c286a5bb7aebabad55`. The compact public projection preserves the raw stream digests, full native argument-vector digests and lint tokens, per-pair original elapsed endpoints, marker state and all program oracles.

The study ran on CPUs 8–11 in its own 3-GiB tmpfs namespace. Recorded minimum headroom was 45.08 GiB home, 40.50 GiB scratch and 29.73 GiB system available memory. The blocking wait was checked with 28 kernel-observed commands. Median observations for immediate, 5 ms, 15 ms and 25 ms were 1.56 ms, 6.64 ms, 16.49 ms, 26.65 ms. Timeout supervision, tracer, hashing and test execution sit outside the wall intervals.

## Verify and run

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py --self-test`. The verifier replays all 128 clock endpoints, both repeat bounds, the native histories and six deliberate corruptions. For a physical rerun use the exact two source-verified PGO Cargo images in the protocol, a verified -18 SDK, the pinned complete Ruff checkout and a populated offline CARGO_HOME. Use two private directories on a quiet Linux x86-64 host with at least 32 logical CPUs and sufficient headroom. Ordinary UID 1000 enters private mount namespaces. The replay produces new local physical measurements.

```sh
python3 -IB replay.py --study /work/new-serde-local --archive /archive/private \
  --sdk /inputs/ohm-18 --ruff /inputs/ruff --registry /inputs/offline-cargo-home \
  --parent-cargo /inputs/cargo-parent --candidate-cargo /inputs/cargo-lint
```
