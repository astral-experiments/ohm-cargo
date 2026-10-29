# Checking Ruff after a package profile edit

Reversing and restoring Ruff's three-line Salsa profile change reduced a warm `cargo check -p ruff_text_size --locked --offline` from 203 ms to 67 ms. The selected crate has no Salsa dependency. Each arm started with an independently writable copy of the same validated warm state. All 32 edited comparisons favored the candidate. [Historical Ruff edit](https://github.com/astral-sh/ruff/commit/57617031de659f0f080d0abbea466b0765f5bab8) · [Cargo PR](https://github.com/astral-sh/ohm-cargo/pull/286)

| Phase | Parent median | Candidate median | Median paired reduction | 95% interval | Candidate faster |
| --- | ---: | ---: | ---: | ---: | ---: |
| Profile edit | 202.94 ms | 66.62 ms | 67.23% | 65.21% to 69.59% | 32/32 |
| First unchanged check | 63.26 ms | 62.68 ms | −0.42% | −4.04% to 1.29% | 15/32 |
| Edit and first unchanged check | 276.12 ms | 128.97 ms | 49.61% | 48.62% to 53.42% | 32/32 |

The paired median measures the percentage change within each pair. The individual time columns give each arm's median. Reversing the edit saved 65.21% and restoring it saved 69.14%. The two-sided sign test for the edited comparison gave p = 4.66 × 10⁻¹⁰. The interval resamples pairs within each edit-direction and execution-order combination. The immediately unchanged interval includes zero. [Registered design](design.md) · [All estimates](reported-statistics.json)

The lockfile retained all 553 packages. The common warm-up compiled one crate. The other eleven native controls each executed only the rustup proxy and Cargo. The entire emitted Rust metadata file had the same SHA-256 on all twelve controls. A separate rustc invocation accepted a real `TextSize`/`TextRange` consumer, and the deliberately missing import produced `E0432` each time. The worker recorded the successful consumer metadata digest and the failing compiler's diagnostic code and text. These external consumer calls were outside the traced Cargo commands and all clocks. [Workload and native checks](workload.py)

The analysis checks 128 raw whole-command elapsed times and their original stdout, stderr and exit statuses. It reconstructs the counterbalanced order from the terminal array and decodes successful kernel exec calls, including resumed calls. The seven operator files omitted from the public archive are identified by digest. Machine-specific paths in native controls have portable replacements. Every measured stream, raw time record and the terminal array remains byte-identical to its original file. [Evidence index](original-file-index.json.gz) · [Matched Cargo build inputs](subjects.json)

Verify the captured results with Python 3.11 or newer.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
python3 -IB check_replay.py
```

To check a local Ruff checkout and the historical hunk, run the following command from this directory.

```sh
python3 -IB replay.py --checkout /path/to/ruff --check-source
```

For a new Linux run with the matched Cargo binaries, supply the two binaries, their Rust SDK, an authenticated offline Cargo registry and a new scratch directory with room for the registry, workspace and warm copies. The caller must be able to use a private mount namespace and supply four allowed CPUs. The public controller uses the same timing body and a separate oracle on every native control. We exercised its source check and verified the original full timing cohort from its captured records. The portable controller did not perform a second full timing run for this packet.

```sh
python3 -IB replay.py --checkout /path/to/ruff \
  --cargo-a /path/to/control/cargo --cargo-b /path/to/candidate/cargo \
  --sdk /path/to/ohm-sdk --cargo-home /path/to/offline-cargo-home \
  --scratch /path/to/new-check-run --cpus 0,1,2,3
```
