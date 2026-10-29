# Wild #48 on #46

This packet compares the full Wild #46 tree at `db821991bd2931dd83e59f236149340ddfc2b427` with that tree plus the ELF unwind writer change from #48 at `925cbbd80297f9054a7d80fd386a1ab2407735e5`. The two captured linker invocations qualified separately. The original full-command attempt stopped during its first native candidate admission. It produced **zero command-level scored rows**.

| Captured linker invocation | Median reduction in Wild instructions | Pairs improved | Exact two-sided sign p | Balanced-order p |
| --- | ---: | ---: | ---: | ---: |
| 181 MB uv library test | 0.3181% | 8/8 | 0.0078125 | 0.0285714 |
| 316 MB uv executable | 0.6740% | 8/8 | 0.0078125 | 0.0285714 |

`compact-focused.zip` is the original independently replayed 170-file archive, byte for byte. It contains the original source archives, two schedules for the complete command, the 34-file implementation manifest, both release product oracles, and the focused raw results. The focused counts cover the linker process. This packet contains no elapsed-time estimates.

`registration-and-rejection.zip` holds the original native admission receipt, the fresh and structural predecessor logs, 25 native-only process records, per-PID exec traces, the rejection traceback, the supervisor/observer/outer-session return receipts, and the source, tool-slot, Cargo-home and bank-retirement evidence. It also contains the prospective recovery registration, reader patch, original independent audits and the 22 recovery-sealed files. `members.json` maps every included source record to its SHA-256. The two eight-pair registration schedules cover fixed body edits in `crates/uv/src/install_source.rs` on uv `c22e6b71933443e9cd299d4b6ac8de035ed4825b`, with `cargo test --no-run --locked --offline -j8`.

The original native command produced the registered 72 test executables and matched the expected process roster of one Cargo, six rustc and five Wild invocations. The process records contain no dynamic instruction totals. The frozen comparator received tuples for the new ELF field positions and lists for the release oracle. Python rejected those sequence comparisons in the first admission. The subject supervisor returned 1, the separate host observer returned 0 and the closed scope contained no remaining workers. The source timestamp, selected tools, Cargo home and vacant target slot were restored. The reader correction reloads the just-written JSON receipt before the same comparator runs. The recovery runner also isolates its own paths and grants. Both original schedules, both full product oracles, and the verifier are byte- or structurally checked against their frozen inputs. This packet ends at the registration of that recovery.

## Exact scope of the retained ELF evidence

Seventy-two of 74 products matched the release oracle byte for byte. The two products below were covered by the pre-existing stock variation rule. The initial cohort registered four eligible paths. Only these two differed. Intervals in the table are zero-based and half-open. Each recorded raw difference is a changed byte within the 32-byte GNU build ID or the low byte of the ELF `.rodata` section header's `sh_entsize` field, from `08` to `00`. The section payload was identical.

| Product under `target/debug/build/uv/` | Retained bytes | Build ID range | `sh_entsize` range | Changed bytes |
| --- | ---: | --- | --- | ---: |
| `e0133cb6050b81d6/out/uv-e0133cb6050b81d6` | 10,398,232 | [896, 928) | [10,396,304, 10,396,305) | 31 + 1 |
| `e6ac92541876a4a1/out/uv` | 316,757,448 | [896, 928) | [316,755,520, 316,755,521) | 32 + 1 |

| Product | Retained SHA-256 | Reconstructed release SHA-256 | Canonical SHA-256 |
| --- | --- | --- | --- |
| `uv-e0133cb6050b81d6` | `b5f86fd37bb9b99ad446c3dd3f8eb40aedecd4e6be69b75b24a8121e889eaa72` | `9bebcd0ade6c7ea4c2705cb647b5a8a54b75cedc759ce6d730f0aab72dedbe90` | `a1ca41b55473e228608cf7a739109e7f43b5bd65be99e2855bb6c66e409de217` |
| `uv` | `327d80c85fd7b674afa66224491799c24e9f6f2a46a617cee4398c08c8fac315` | `3b4d11037c4d78e0b28b38c0b5c9ca1d8e4f632575eac0d4b3c2c93135d1d248` | `20b57d1673bc379cbd703f4be27540e45b61365267f018ab2520beb77fe12306` |

The 327,155,680 diagnostic ELF bytes remain in the original host's `stack-pr46/recovery/products/<retained SHA-256>` store. The on-host diagnosis hashed each complete file, then reconstructed the original release hash by substituting only the two recorded fields. The portable verifier checks the recorded hashes, changed-byte positions and values against the admission and release manifests. Repeating the complete byte reconstruction requires the host objects.

## Replay with Python 3.11 or newer

Run these commands from this directory. They need only the two archives and Python's standard library. The two scorers only read data.

```sh
sha256sum -c SHA256SUMS
scratch=$(mktemp -d)
python3 -m zipfile -e compact-focused.zip "$scratch/focus"
python3 -m zipfile -e registration-and-rejection.zip "$scratch/kit"
python3 -I -B "$scratch/focus/verify-fresh.py" build-focus
python3 -I -B "$scratch/kit/verify.py" "$PWD/compact-focused.zip"
```

`replay.json` records a fresh extraction with source and diagnostic-store access denied. It reproduces the original tuple/list rejection, all 74 canonical product matches with the JSON reader and rejection of both a one-digit change in an ordinary product digest and a one-byte shift in an allowed position. It includes the exact offsets for all differing bytes, the cold/native scope closure and the independently recomputed linker results. No subject executable runs during this replay.
