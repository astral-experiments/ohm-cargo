# A real active development-profile edit in Ruff

Both PGO Cargo builds compiled Ruff after its active development profile changed. The candidate reused the workspace resolver on all four affected check/test transitions. The older Cargo ran a full resolution on each. On the first edited check, the older process performed **one full resolution and one hit**. The candidate performed **zero full resolutions and two hits**. Both really dispatched rustc. These are correctness and launch observations. The study collected no scored timings.

The source was Ruff at `93526150df078af7dd8fc4226cdcc469539d2001`. The experiment reversed the entire six-line root-manifest change from “Optimize development builds by default” and then restored it. That historical commit also touched other files. Both arms used the same checkout and offline registry, separate fresh per-arm overlays at the same absolute path, a 553-package lockfile, private check/test targets, and stock released -18 Rust and Wild on Linux x86-64. The independent Cargo images are private release-profile PGO builds, both carrying the same version stamp. Their actual binary/commit identities, the compiler/driver/linker bytes, the Ruff Git objects and the full manifest projection are bound in `subjects.json`. [Ruff source](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [historical edit](https://github.com/astral-sh/ruff/commit/36cc91ffb72adde11f0c4dfb76330a07481f6153)

## Native outcomes

There were 32 ordinary Cargo commands across both arms, 18 checks and 14 serde integration-test builds. Four checks intentionally failed. Each arm ran 66 source rustc compilations, 16 build scripts and 24 actual stock links; every link went through `cc`, `collect2` and the enrolled Wild `ld.bfd`. The checker independently reconstructs all 476 successful process launches from the two arms’ kernel traces, including 58 split/resumed calls. The rustup proxy and the selected Cargo are separate launches of each logical Cargo command.

| Stage in each arm | Full resolutions / hits, A → B | Real compilations / Wild links in both arms |
|---|---|---|
| Original check; original test build | 1/0 → 1/0 each | 1/0; 15/6 |
| Unchanged check; unchanged test build | 0/1 → 0/1 each | 0/0 each |
| Reverse profile and check | 1/1 → 0/2 | 1/0 |
| Reverse profile and test build | 1/0 → 0/1 | 15/6 |
| Unchanged check; unchanged test build | 0/1 → 0/1 each | 0/0 each |
| Empty edited check; empty edited test build | 1/0 → 1/0 each | 1/0; 15/6 |
| Introduce type error; empty check of error | 0/1 → 0/1; 1/0 → 1/0 | 1/0 each, Cargo 101 |
| Restore, check; restore, test build | 1/0 → 0/1 each | 1/0; 15/6 |
| Final unchanged check; final unchanged test build | 0/1 → 0/1 each | 0/0 each |

The actual selected units reported optimization levels 1 before and 0 after reversing the profile, with line-tables-only debug information in both. The serde test executable changed from SHA-256 `fe73259b0f12928fcce37ab700ff2b52656b7a18c1c45f075c7b4272955f2dee` to `a2a35c107b1ea2ed5891cf759effdedeeac0b0d044cc762a70c3e1822b2ffe09`. Both independently empty edited builds produced that same entire executable. Both restores recovered the original SHA. Fourteen live harness listings and runs produced 42 passing tests in total: `invalid_range_deserialization`, `range_serialization` and `size_serialization`. Warm and empty E0308 checks both fail on line 38, highlighting the integer at columns 39–41 and the expected type at columns 34–36. The complete rendered diagnostics, primary and secondary spans, failure note and user-facing error lines agree across all four failures.

All 16 pairs of typed Cargo streams agree as multisets after replacing only the per-Cargo namespace in declared output paths. This comparison retains the entire build-script messages, target profiles, diagnostic messages, library filenames, eligibility and freshness. Within each arm, the edited warm and empty graphs have 23 of 24 matching raw test-product hashes. The `ruff_text_size.rlib` differs. The same distinction occurs on original versus restored. Between Cargo images, 16 of 24 product hashes match at every successful test stage. The four differing pairs of rlib/rmeta belong to `ruff_text_size`, `serde`, `serde_core` and `serde_test`. No digest is normalized. Every compared path, SHA, package and role is retained in `product-comparisons.json.gz`. The private tmpfs vanished at process exit, so this report can verify the original whole-file digest receipts, native tests and typed records. It cannot attribute the internal byte differences retrospectively. The check-only rmeta hash does agree across arms and across corresponding source states.

## Read and replay

Run the verifier with Python 3.11 or later from this directory.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
```

`streams.json.gz` retains every stdout/stderr line, strace exec record, typed raw product hash, harness listing and verdict. Literal private roots were mapped to `<arena>`, `<sdk>`, `<proxies>` and `<driver>`. The registry storage bucket is `<registry>`; crate names and checksums remain. Full raw file hashes and sizes are in `raw-file-index.json.gz`, including all 161 files in the accepted run, and `complete.json` is the original unchanged terminal. The raw successful argv digests were calculated before redaction. The verifier reassembles all public raw trace lines and checks their events and argument shape against those original records. It also tests seven deliberate evidence corruptions. `project.py --help` describes regeneration when the original files are available.

For a fresh Linux rerun, supply these two actual Cargo images, an installed -18 SDK, rustup proxies, a clean Ruff checkout at the pin (with the historical Git object), and an offline Cargo home with the locked dependencies hydrated. Use an ordinary account with passwordless sudo for the mount namespace, and a filesystem supported as an overlay lower. The work and report destinations must be absent, with existing parents. `--reserve-gib` sets your own report-filesystem free-space floor. A private 3 GiB tmpfs supplies the same alias, fresh overlay, distinct check/test output roots and separate empty controls for each arm. The ordinary Cargo child drops capabilities before invoking `cargo +ohm`. Results including failed launches stay in the supplied report directory.

```sh
python3 -IB replay.py --check-source "$RUFF"
python3 -IB replay.py --checkout "$RUFF" --sdk "$OHM18" \
  --control "$CARGO_A" --candidate "$CARGO_B" --cargo-home "$OFFLINE_CARGO_HOME" \
  --proxies "$RUSTUP_PROXIES" --work "$RUN/empty-arena" --out "$RUN/reports" --reserve-gib 5
```

The source-only replay command was independently executed. The 32 native commands whose results are reported here ran through the original study driver. The portable adapter preserves its Cargo invocation and stage sequence, with parameters for local paths and account. An independently repeated run on another system can produce different physical file hashes.

## Setup attempts

The first attempt stopped at the rustup `cargo -Vv` preflight, before any recorded check/test command. Only the returned portion of the launcher traceback was available. There is no original on-disk worker stderr or final errno. The second attempt set HOME after sudo, reached Cargo, and ran five real commands, all retained. Its classifier rejected the last command because it saw a cache hit even though the same process had already performed a full resolution. In that primary stderr the full-resolution line is 1 and the hit line is 1108. The corrected v3 classifier counts both events independently. Neither setup attempt contributes to the 32-command result.

The pinned workspace, crate sources, lockfile and patch are distributed under `RUFF-LICENSE`. The scoped Cargo comparison uses the repository's MIT/Apache-2.0 terms.
