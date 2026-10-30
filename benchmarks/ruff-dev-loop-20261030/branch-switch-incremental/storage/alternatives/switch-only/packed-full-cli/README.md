# Allocated storage across a full Ruff CLI branch switch

On the first switch, branch retention in Rust #274 used **2,900.83 MiB** versus **2,407.44 MiB** with retention off. Packing old codegen objects reduced that to **2,768.66 MiB**, still **15.0% above Off**. After both returns the packed build used 2,300.45 MiB, close to Off at 2,302.11 MiB. Its largest observed post-command state was 258.47–258.65 MiB above Off’s own maximum in each triplet. These are settled allocations. The experiment sampled neither in-command high-water storage nor full CLI times.

| Source and command mode | What rustc retained |
| --- | --- |
| Off, `eb15cd3dc0ab0404f8ad18589569e05a70a4d401`, default flags | The latest finalized incremental session per crate. |
| Full, `b676a640c76193a0e241d2517a64e37e156659b9`, branch cache enabled | The current head of Rust #274, with up to two finalized sessions per crate. |
| Packed, `eb15cd3dc0ab0404f8ad18589569e05a70a4d401`, branch cache enabled | The separate experimental follow-up to #274, with up to two finalized sessions and compression of eligible older native objects. |

Off and Packed ran the same driver. Full ran the driver built from the published PR head. Both SDKs used the identical signed Cargo `2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c`, Wild and standard library. The experiment did not enroll a second Off arm on b676. The QA checkout contains the precise compiler source transport. [Rust #274](https://github.com/astral-experiments/ohm-rust/pull/274) · [Frozen qualification source](https://github.com/astral-experiments/ohm/tree/99dd1ed50dc39354707148ed77ec2ec5d8235978/scripts/ohm-packed-ruff/full-cli)

All six fresh triplets passed the predeclared ≥32 MiB and ≥1% Packed-over-Full reduction on each of four endpoints. The six orders cover all permutations on a single Linux x86-64 runner after a separate two-triplet pilot. Each arm installation started with empty target and shared-build directories. Every settled state includes all allocated blocks in both directories after filesystem synchronization, counting each device/inode once. GNU stat, find, du and a Python ledger agreed. The calibration included sparse files, hardlinks across the two roots and a dangling symlink.

| Post-command state | Off median MiB | Full (#274) median MiB | Packed median MiB |
| --- | ---: | ---: | ---: |
| Cold A | 2,300.44 | 2,300.45 | 2,300.45 |
| First B | 2,407.44 | 2,900.83 | 2,768.66 |
| Return A | 2,510.06 | 2,557.62 | 2,292.99 |
| Return B | 2,302.11 | 2,565.19 | 2,300.45 |
| Unchanged B | 2,302.11 | 2,565.19 | 2,300.45 |
| Repair B after expected E0308 | 2,310.32 | 2,771.24 | 2,632.87 |

At the first switch, Packed saved 132.07–132.27 MiB compared with Full. The exclusively held A session still included 482.21 MiB of ordinary dependency graphs, 216.78 MiB of query tables and 172.28 MiB of native objects. The new B session held the first packed files. After both branches had been revisited, both sessions contained packed files. On the separate recovery, Packed still used 13.96% above Off. The ledger includes the failed compilation state as well as the repaired one.

The 169-path historical Ruff change went from `b5dba861cc38e3f7fb4524c9ceba3e01a474ea13` to `7b13f01ba1569887a25670820764b24c206da8e5`. Each successful `cargo +ohm build -p ruff --bin ruff --locked --offline -j4` reported 375 artifacts. The 108 CLI and typed native reader results matched independent same-role empty builds byte for byte, including repairs after all 18 expected compiler errors. Actual Ruff checks, f-string edits, 64/56-byte AST sizes and their contradictory probes distinguished the two versions. Separate native-provider replacement, corruption and repair passed in all three arms. The 57 held-out physical process traces showed real incremental code generation on all 20 compilers on each observed return, and zero compilers or linkers on every unchanged B.

## Readback

Run with Python 3.9+ and the zstd CLI.

```sh
python3 -IB verify.py
```

`ledgers.zst` carries the complete original path and inode/size/mode/block records for all 126 held-out states. `observations.zst` carries the original allocation-reader outputs, Cargo argument/exit and typed artifact records, native digests and behavioral verdicts. Both streams frame raw original files with a UTF-8 name, tab, byte length and newline, followed by exactly that many bytes. `members.json.gz` records their sizes and SHA-256. The reader independently recomputes allocation in both roots, all 24 paired contrasts, unique aliases, the 375-unit visits and unchanged kernel receipts. `confirm-ownership.json.gz` breaks down older-only bytes by file type. Source and binary identities, raw instruction/section hashes and process attribution are in `confirm-native.json`, `native-elf.json.gz` and `confirm-incremental.json.gz`.

The original pilot ZIP has SHA-256 `51fb156eb4c1b57f2c3f9ec5ee456eaecd6762a28fa518c356c1d223f45ebad4`; it includes the complete native executable bodies, provider controls, calibration and frozen measuring source. The held-out ZIP has SHA-256 `e9fcdd65d0244f5a03f115a3b1640a1c79386b06722b082959f87ec0f8c47518` and includes all original kernel and Cargo streams. GitHub’s recorded artifact expiry is November 6, 2026. The two adopted ZIPs were also retained separately on the coordinator. [Original pilot](https://github.com/astral-experiments/ohm/actions/runs/41063598665/artifacts/12984940261) · [Original held-out runs](https://github.com/astral-experiments/ohm/actions/runs/41063598665/artifacts/12987886884)

Three preceding acquisitions stopped on changed debug paths under a reinstalled driver, an unconditional checkout that touched an unchanged Git input, and a still-young failed incremental session. The successful qualification preserved driver inode and ctime, checked unchanged Git inputs, and reserved an eleven-second age/lock check exclusively for error recovery. No earlier samples enter the table. [Driver identity](https://github.com/astral-experiments/ohm/actions/runs/41054355399) · [Unchanged Git input](https://github.com/astral-experiments/ohm/actions/runs/41057286869) · [Failed session](https://github.com/astral-experiments/ohm/actions/runs/41060426848)
