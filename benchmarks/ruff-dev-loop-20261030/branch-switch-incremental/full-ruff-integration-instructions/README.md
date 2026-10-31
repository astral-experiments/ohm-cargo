# Building Ruff’s integration tests after a branch switch

Twelve fresh Linux workers each built Ruff’s 390-unit `integration_test` target using the default compiler configuration and the same compiler with `-Zohm-branch-cache=yes`. Every measurement covered the full Cargo process tree, from invocation to exit. The 96 integration tests and their subprocess checks ran after that counter closed. The two pilot hosts contributed no observations. [Registration and native reader](https://github.com/astral-experiments/ohm/tree/679e72fedd4968636469d958c38225c0ce3fefab/scripts/ruff-integration-pmu) · [Original run](https://github.com/astral-experiments/ohm/actions/runs/41235234268)

```sh
cargo +ohm test -p ruff --test integration_test --no-run --locked --offline -j4 --message-format=json
```

| Command | Default, billion instructions | Retention, billion instructions | Median paired default / retention |
| --- | ---: | ---: | ---: |
| Initial A build | 2,704.32 | 2,704.32 | 1.0000× |
| First switch to B | 858.59 | 911.10 | 0.9423× |
| Return to A | 859.72 | 111.99 | 7.6771× |
| Return to B | 861.25 | 138.95 | 6.1982× |
| Both returns | 1,720.95 | 250.94 | 6.8579× |
| Unchanged B | 6.23 | 6.23 | 0.9998× |
| Invalid edit on B | 1.95 | 2.60 | 0.7501× |
| Repair on B | 57.91 | 82.06 | 0.7056× |
| All seven commands | 5,349.99 | 3,957.27 | 1.3519× |

The counts are medians across workers. Ratios use the pair from each worker, including sums across multiple commands. Six workers ran the default first and six ran retention first. All twelve completed the preregistered first attempt. The three planned intervals use paired ranks 2 and 11. Their exact marginal coverage is 99.3652%, with simultaneous coverage of at least 98.0957%.

| Planned endpoint | Paired median | Ranks 2 and 11 |
| --- | ---: | ---: |
| Return to A | 7.67709× | 7.67428–7.67842× |
| Return to B | 6.19824× | 6.19693–6.19930× |
| Both returns | 6.85789× | 6.85684–6.85939× |

Retention used +498.9 MiB after the first switch, +264.8 MiB after the unchanged visit, and +467.9 MiB after repair. The median of each worker’s largest visit-end allocation was 2.614 GiB with the default and 2.998 GiB with retention. These values count distinct allocated inodes across the target and build directories after command exit.

The raw Cargo output, retired instructions, clock boundaries, test names, child-process receipts, native comparisons and allocation ledgers are in the compact packet. It includes the verified hashes and sizes of the executable bodies. The original archives below contain the bodies themselves. Both readers checked that all 96 listed tests passed, that two selected tests launched the CLI, and that each successful build matched the clean executable hashes for its revision. The deliberate Rust error failed at the enrolled source line.

## Reproduce the counts offline

From this directory, run the following with Python 3.11 or newer.

```sh
sha256sum --check SHA256SUMS
python3 -IB score_packet.py ruff-integration-confirmation.tar.xz --match direct.json --official registered.json > /tmp/ohm-ruff-integration-counts.txt
cmp counts.txt /tmp/ohm-ruff-integration-counts.txt
```

## Original native records

| Position | Job | Archive | SHA-256 |
| --- | --- | --- | --- |
| 01 | [124637562310](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562310) | [13056336723](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13056336723) | `6640e2c4fcbacd054d21f18ff47d49932b12750754312f3c687614768b337ff1` |
| 02 | [124637562320](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562320) | [13055901598](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13055901598) | `ba52c06c86b3074bf998add6bd4e562ab6e965591948ffa3d6e8a36f65652133` |
| 03 | [124637562269](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562269) | [13055841631](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13055841631) | `0b5937cbb97414bd7526ec7679fc4c2231de3a1a1e4d442c014f15cf80921809` |
| 04 | [124637562411](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562411) | [13055462473](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13055462473) | `cf1a6dfb6a6c9eec6855da7d08567942221ac57e7f21d97d8cc47e4178dd8e2e` |
| 05 | [124637562386](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562386) | [13055843686](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13055843686) | `fd57c516a7c5ac6684ea7478c06461496981cf4b0d7e681e86fae030620c7c6d` |
| 06 | [124637562347](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562347) | [13057045004](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13057045004) | `f9a5b58ff78d4625459c3ef288827f50f450a67b428083c0b7f232c72fa38526` |
| 07 | [124637562344](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562344) | [13056786137](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13056786137) | `9969cf9268dc6c2dd47d156ad9c10d4b995400c548d53a6b104f9852aa3e710e` |
| 08 | [124637562356](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562356) | [13055714385](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13055714385) | `557f1477a25f33a2c8daa63d183912a920b6090d637ba2c77a098195c98a9e60` |
| 09 | [124637562279](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562279) | [13057665056](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13057665056) | `cfbef72862102f2b57ca77133927507ed22c92408b5ccfdc26349d9ce04c0edd` |
| 10 | [124637562289](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562289) | [13057211268](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13057211268) | `1412b00ddfb6096522f017a6b16596d03729e0e6ecfa98231e65bb6ed5de0e50` |
| 11 | [124637562313](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562313) | [13057560757](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13057560757) | `8776f5b94af17e9acc48deddbf4ee2cde2f3b7a498fe0d17c284f658d33159c0` |
| 12 | [124637562308](https://github.com/astral-experiments/ohm/actions/runs/41235234268/job/124637562308) | [13056799376](https://github.com/astral-experiments/ohm/actions/runs/41235234268/artifacts/13056799376) | `8ee9706a1327db08c20a7a44652218ecb0835106aad5a388b94965d1b70f3677` |
