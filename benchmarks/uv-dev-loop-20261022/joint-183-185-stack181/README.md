# Combined PR183–185: Cargo instruction counts on uv

The combined parser, scheduler and package-ID changes reduce Cargo-process instructions by **3.54% for `cargo check`** and **4.20% for `cargo test --no-run`**, measured directly against PR181 on warmed, unchanged uv. These are instruction-count results; native wall-time speed and regressions remain unverified.

| Required primary endpoint | Reduction | Paired 99% bootstrap interval | Wins | Two-sided sign p |
| --- | ---: | ---: | ---: | ---: |
| `check` | 3.54% | 3.50%–3.65% | 12/12 | 0.00048828125 |
| `test --no-run` | 4.20% | 4.15%–4.30% | 12/12 | 0.00048828125 |

The prospective decision requires both endpoints to pass: at least 1% reduction, a positive 99% lower bound, sign p at most 0.01, and positive effects in both AB and BA orders. Each endpoint has twelve independent pairs, balanced six AB/six BA, plus two warmup pairs excluded from inference. All 56 full Callgrind profiles are retained. The bootstrap uses the original linear quantile, 20,000 resamples and seed 1701. The fixed check/test order seeds are 20261022151 and 20261022152. No observations were excluded, replaced, pooled or added.

Run the read-only replay from an unmodified copy of this directory using Python 3.12 and its standard library:

```sh
python3 -I -B reproduce_counts.py
```

The command authenticates every published file and archive member, reconstructs all JSON/JSONL/CSV/profile joins, checks the exact plans, commands, environments, binary/configuration identities, original runtime aliases and complete zero-child preflight traces, then recomputes both effects and gates. It uses only these published bytes; it does not execute Cargo, rustc, tests, Git, a benchmark, or a network operation. Instrumented elapsed-time fields are checked only for original table/log integrity and are not analyzed as performance effects.

`raw-ir.tar.gz` preserves 432 original members with their exact names, bytes and regular-file metadata: 430 collected files plus the unchanged original transfer manifest and completion record. The only omission is `remote/delivery-occupancy.json`, an unrelated private process snapshot. This file **is an original sealed provenance input**. Its original 861-byte/SHA256 entry remains in the transfer manifest, measurement seal and both 847-entry immutable-input hash maps. The complete 433-member original collection, including that file, was authenticated locally before effects. Public replay acknowledges that it cannot rehash this one private payload. The exact selection decision and conservation map are included. Original collector-excluded binaries, caches and targets are represented by their original identity records rather than republished payloads.

The adapter keeps original records distinct from derived indexes. Its only namespace mapping removes the literal `remote/` prefix and resolves the exact original cohort root to an authenticated in-memory member. It does not rewrite paths, flags, samples, profile counters, or configurations. The original seed-only portable checker, complete original runner/reviewer source, strict trace parser, and exact reused raw-validation functions are included under `harness/`. The statistical functions and complete final gate block remain unchanged.

The source comparison is PR181 `d81a093becb4321a975522624c2a383970f0d164` (tree `c4178b67e0b3a64a12b9b58f84b97323b99d734e`) to combined commit `0116a6d29f506f425d837348b26d40d6a668027d` (tree `86a812c401f6a8966e5d9f428775f280c19b7b90`). The combined tree contains [PR183](https://github.com/astral-sh/ohm-cargo/pull/183), [PR184](https://github.com/astral-sh/ohm-cargo/pull/184), and [PR185](https://github.com/astral-sh/ohm-cargo/pull/185); PR182 is excluded. All eight required jobs in [exact-source CI39696693562](https://github.com/astral-sh/ohm-cargo/actions/runs/39696693562) passed. These are direct combined measurements, with no summed individual-PR claim.

Both Cargo variants came from a fresh matched production pair using stock Rust1.99, release opt3, ThinLTO, one codegen unit, `all-static` plus `ohm-defaults`, no PGO and disabled incremental compilation. Debug information was retained during compilation and then stripped with allocated sections proven unchanged. The baseline/candidate SHA256s are `4a80fa441367b53cc8489b126452865a441ef37fe4c59a0ace3fb7d5e3660ae6` and `adeb8f94e62340b14a4bda2456b1b692b1c3083b9df4195c1da4d252fb7ea09a`. Both variants used the same physical producer source/target/cache paths. Their common embedded Git HEAD `5e5d271d763d7beb38b48755e22bd59e93f02b97` is distinct from the actual source trees above. The full producer patches, exact driver/manifest, provenance and strip proofs are retained in the archive; the incremental source patch and source bundle are also provided separately.

The unchanged uv commit is `3d82a6ad5a7eab8c68236553b7846517767c4b61`. Each sample runs Cargo with `-Zohm-defaults=yes`, `--locked --offline -j 8`; test uses `--no-run`. Callgrind3.22 counts only the Cargo process with `--trace-children=no`. Fixed warming, successful cross-switch calls, fresh stderr and complete exec traces establish that these are warmed Cargo dev-loop overhead measurements, with no compiler/build-script/test execution in the measured workload. The exact original configurations and protocol provide the remaining settings.

Earlier host4 and host8 attempts are excluded as whole attempts. The host4 partial attempt remained unqualified with its samples opaque; the host8 local entry failure record does not claim that remote state was independently verified. Their original closure identities are retained under `history/`; none of their observations enter this cohort. The source-only publication plan was frozen and independently reviewed before the concrete evidence adapter was prepared.

