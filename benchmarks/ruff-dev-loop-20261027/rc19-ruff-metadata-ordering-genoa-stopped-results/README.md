# Genoa pending-metadata timing cohort stopped at its private storage floor

**The registered Genoa performance result is unavailable.** Two adjacent pairs passed every check. Both visits of the third pair ran their two ordinary Cargo commands, then the 17 GiB private Btrfs volume reported 1,047,527,424 bytes available at the first post-pair check. Its preregistered minimum was 1,073,741,824 bytes. The 25 MiB shortfall preceded the independent reader, so the worker stopped. The separate home and scratch floors passed.

| | Observed |
|---|---:|
| Registered pairs | 32 |
| Pairs with complete product and reader validation | 2 |
| Additional pairs with both ordinary visits and incomplete postchecks | 1 |
| Later pairs that never started | 29 |
| Ordinary Cargo commands that returned 0 with 510 typed units | 12 |
| Complete valid / invalid E0609 / recovered reader sequences | 4 |
| Scorable host series | 0 |

All six visits produced the registered source changes, complete typed inventories and accepted AST/index metadata at the end of the ordinary commands. The first four visits also passed the full 597-file ledger and external same-generation Ruff reader. The final two received no subsequent qualifying reader. The original stricter admission had already stopped independently on four genuine output-byte differences. Both records remain separate. All three pairs are excluded from two-host performance estimates. There were no replacements or changes to the storage rule. [Native qualification](https://github.com/astral-sh/ohm-cargo/tree/04d0d3730a96d2b1e887d61a0ca40fdaca6d5a40/benchmarks/ruff-dev-loop-20261027/rc19-ruff-metadata-ordering-genoa-release-qualification) [Prospective supplement](https://github.com/astral-sh/ohm-cargo/tree/4deb844b69da49d2024f4a0efc17f2bb89edd9cc/benchmarks/ruff-dev-loop-20261027/rc19-ruff-metadata-ordering-genoa-clock-supplement)

The packet preserves the twelve raw clock readings, source and command digests, input and output identifiers, all Cargo rosters and receipt bindings, and the four completed reader and product inventories. For the incomplete pair, a separate read-only archival pass on its retained snapshots collected the 597 literal file digests, 30 source digests and four named variant bodies per visit. It ran no Cargo, rustc or program and supplied no eligibility decision. An initial read-only mount attempt failed before capture. Recovery used a kernel read-only loop device and a read-only mount, with no-atime file reads. The raw variant bodies remain in the private volume and recovered local custody. The public data identify the complete bytes by SHA-256.

Run `python3 -IB verify.py` beside the manifest to check the exact predeclared prefix, the twelve successful calls and the stopping condition.
