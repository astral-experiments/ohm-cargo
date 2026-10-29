# Wild #48 measured directly on Wild #46

Run the following command in the extracted archive using Python 3.11 or newer.

    python3 -I -B verify-complete.py

The verifier checks the manifest, reconstructs both Git source trees, hashes both measured linker binaries, replays the frozen focused and complete-command scores and checks the native exec records. It verifies the prior stock controls and reconstructs both historical raw ELF digests from the actual rejected admission’s retained products.

## Complete edited Cargo commands

Every command built tests without executing them. Each fixture uses distributed Ohm -18 Cargo plus rustc and counts every instruction across one Cargo, six rustc and five Wild processes. Both arms emit the same 72 named tests. The source-edit fixtures, each with eight balanced pairs, were registered before their first performance sample. These records measure instructions.

| Edited uv fixture | Median saving | Winning pairs | Two-sided sign P | Balanced-order P | Raw paired matches | Canonical paired matches |
|---|---:|---:|---:|---:|---:|---:|
| initial-base | 0.213494% | 8/8 | 0.0078125 | 0.0285714 | 586/592 | 592/592 |
| replica-base | 0.214333% | 8/8 | 0.0078125 | 0.0285714 | 587/592 | 592/592 |

The only permitted raw variation is the previously stock-reproduced 0/8 ELF section-header byte and its 32-byte dependent GNU build ID at the same offsets. Each command also compares all 74 products with the earlier exact per-edit release oracle. The first fixture’s superseded native-only admission and the narrowly corrected JSON reader are preserved under recovery/.

## Focused checks

The two captured single-worker links saved a median 0.318124% and 0.673998% of instructions. All eight pairs improved for each input. Every scored linked file matched the registered raw SHA-256. The candidate passed 184 libwild unit tests, seven native integration cases across six groups and five normal/malformed ELF probes. The tiny third link has one descriptive pair and no statistical gate.

## Files

Both measured executables are under bin/. The two source archives and the exact one-file patch are under source/. compact-focused.zip contains compilation logs, official QA and raw captured-link counts. command-v2/results contains the corrected command cohorts, raw argv, full per-thread counters, product hashes and native strace files. release-evidence contains the stock path proof, earlier per-edit reference receipts and their membership in the release evidence manifest. capture-inputs gives the large captured inputs’ identity and argv for recapture. The complete captured object files and 72 emitted uv test binaries are represented by digests. The two actual ELFs used to diagnose the superseded admission are included under recovery/products/.
