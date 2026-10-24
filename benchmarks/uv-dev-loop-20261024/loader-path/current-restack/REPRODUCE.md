# Verify and reproduce the exact-restack #178 experiment

This packet contains the complete valid current confirmation and an authenticated replayable subset of its preparation/build evidence. The commands below verify it and describe an independently rebound fresh experiment. Original absolute paths and hashes are historical provenance; a fresh host needs its own inputs, receipt paths and authority. Do not fabricate native provenance or reuse a previous execution's approval.

1. **Verify the completed evidence before analysis.** The original publication verifier is included byte-for-byte as `verify.py`. Run:

   ```bash
   python3 -I -B verify.py
   python3 -I -B verify.py --extract /absolute/new/evidence-copy
   ```

   It checks every publication file, the compressed archive and every decompressed member against an external SHA256/size manifest. It rejects unsafe paths, links, duplicate members and missing or extra files. It executes no archived program. Recompression preserves all original member bytes. The historical experiment is linked separately and never enters the current analysis.

2. **Release the raw gates, then replay the original statistics.** Require the exact persistent-owner job and complete collector terminal, successful restoration of the baseline native snapshot, unchanged input/source/runtime identities, all twelve prescribed pairs and all 24 command results. Join each immediate post-return raw receipt to the matching sample's command, cwd, exit code, elapsed value and raw stdout/stderr paths. Authenticate both raw streams through the member manifest; require the fixture validation and per-sample restoration joins. Check all retained pair admissions and before/after service-cycle records. An incomplete or operationally invalid block remains unopened for effects.

   The included `replay_raw.py` performs the retained raw checks using only extracted files and the unchanged pure helper functions. Its path/CLI/output-only delta reverses byte-for-byte to the original auditor. It runs no workload or host observation. After extraction, run:

   ```bash
   python3 -I -B replay_raw.py /absolute/new/evidence-copy > /absolute/new/raw-gates.json
   ```

   Require `state=passed`. Then copy only the authenticated `manifest.json` and `samples.json` into a new directory because the analyzer writes `analysis.json`:

   ```bash
   mkdir /absolute/new/analysis-copy
   cp confirmation/manifest.json confirmation/samples.json /absolute/new/analysis-copy/
   python3 -I -B tools/paired.py analyze /absolute/new/analysis-copy \
     --confidence 0.99 --resamples 20000 --seed 1701 \
     --minimum-pairs 12 --minimum-improvement 0.01
   cmp confirmation/analysis.json /absolute/new/analysis-copy/analysis.json
   ```

   The statistical unit is a whole restored-state pair. The 1% threshold applies to the point reduction; the 99% speedup interval must be wholly above 1. The sign test and both AB/BA subgroup conditions also apply. No all-wins rule or additional samples are introduced. Child CPU statistics are secondary. Actual compiler/build-script counts come from the retained Cargo JSON and verbose command records, not from elapsed-time inference.

3. **Rebuild the exact source pair at common physical paths.** Create a disposable `astral-sh/ohm-cargo` checkout, private producer package home and build target. Install stock Rust 1.99.0 and the native build dependencies recorded in `build/`. Keep the Git HEAD at `5e5d271d763d7beb38b48755e22bd59e93f02b97` in both arms; apply the recorded patches to the index and working tree:

   ```bash
   git -C "$CARGO_REPRO_SRC" checkout --detach 5e5d271d763d7beb38b48755e22bd59e93f02b97
   git -C "$CARGO_REPRO_SRC" apply --index "$EVIDENCE/build/base.patch"
   git -C "$CARGO_REPRO_SRC" write-tree
   git -C "$CARGO_REPRO_SRC" diff --exit-code
   ```

   The baseline tree must be `6919395c3f4732ade7d263db1d5b64fd7562845e`. Build it and preserve the full binary before the next build. Reset this disposable checkout to the same common HEAD, apply `base.patch` and then `loader.patch`; the candidate tree must be `45280a180bb4bea53c79d423c7cc71255dfe81c3`. Require no untracked source files and exact trees again after each build. Both Cargo lockfiles have SHA256 `c49cc3e6fb251810e84f945711ef5c7e4dab57ab395918873133a3704c3fc2f3`.

   The exact production command, pinned to producer CPUs 24–31, is:

   ```text
   {stock-1.99.0}/bin/cargo build --release --locked --bin cargo \
     --features all-static,ohm-defaults -j 8 -v
   ```

   Start with only the existing `HOME`, `USER`, `LOGNAME`, `SHELL`, `LANG`, `LC_ALL` and optional `TZ`, then set the producer environment from `build/matched-build-recipe.json`, adapting owned paths consistently. In particular, preserve **all** of these settings:

   ```text
   CARGO_BUILD_JOBS=8
   CARGO_INCREMENTAL=0
   CARGO_PROFILE_RELEASE_OPT_LEVEL=3
   CARGO_PROFILE_RELEASE_LTO=thin
   CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
   CARGO_PROFILE_RELEASE_DEBUG=1
   CARGO_PROFILE_RELEASE_INCREMENTAL=false
   CARGO_PROFILE_RELEASE_STRIP=none
   CFG_RELEASE_CHANNEL=dev
   LIBZ_SYS_STATIC=1
   CARGO_TERM_COLOR=never
   ```

   Bind the actual stock `RUSTC`, `RUSTDOC`, `PATH`, private `CARGO_HOME`, common `CARGO_TARGET_DIR`, temporary directory, task-owned Git config and SSL certificate paths. Do not inherit extra `RUSTFLAGS`, compiler wrappers, C/C++ flags or PGO settings. The recorded command does not add `--offline`; its archived closure was already cached. Workload commands below do use `--offline`.

   Keep each full binary, create a separate `objcopy --strip-debug` copy, set both modes to `0755`, and compare all allocated ELF sections with the existing `allocated_sections` function in `audit-tools/strip_binaries.py`. The full binary must remain unchanged. Record `-Vv`, actual dynamic libraries, tools and complete source identities for both builds. The `all-static` feature still leaves system runtime libraries dynamically linked. Both recorded `-Vv` outputs omit commit fields: the common checkout HEAD is provenance, not an emitted-version claim. New paths or tools can produce different binary hashes.

   `audit-tools/build_remote.py` and its common helper retain the actual build sequence and environment construction. Their paths and prerequisite receipts describe the recorded private root; they are audit sources, not self-contained installers.

4. **Create a fresh private uv fixture.** Use Linux x86_64, eight workload CPUs, Python 3, Git, GNU `cp`, `rsync`, `taskset` and the required native compiler/linker tools. Allow space for two roughly 16.4 GB logical native snapshots, one live tree, source/package inputs and build outputs. Checkout uv `3d82a6ad5a7eab8c68236553b7846517767c4b61`; its lockfile SHA256 is `747296375bb1889689f3bbb1e0303bddd071d6a65117c00be50856448260d014`.

   Use the original Ohm SDK6 archive, SHA256 `98a4f4f99ea1ff36e10209258724426496afbbcab14d746294fe53a2fedad37c`. Bind the full runtime and actual symlinks. Rustc is commit `6d4a7ee3200c5311112d433cb9d1da4a2630a66f`, executable SHA256 `6109cff145371a50c4f62b61908d2ffbf6d259b180c8effde07baa426aab682a`, driver SHA256 `a3a5d8cc86af464504170220d142c4ea1129434e2d5e741755feec6f9f35a436`. Its real Wild path is `lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd`, SHA256 `5b2baebf62de0f8c185711b808c3f553da3b7166b1c289420df5276b027f5597`.

   Populate a source/archive-only package cache sufficient for locked offline uv builds. Copy no compiled state, credentials or user configuration. Place the frozen helpers under `BENCH_ROOT/work/benchmark/`; `loader_fixture_delta.py` derives its base from this layout. Adapt `protocol/native-template-02.json` into a new template, pinning both variants, the uv checkout, SDK, actual inherited Cargo configuration, dynamic libraries, host tools, certificates and helper sources. The template's input `CARGO_HOME` becomes a private package-home copy at initialization. Keep LD/DYLD/preload/audit paths unset as recorded; explicit empty values are a different input.

   Both variants must share the same absolute canonical Cargo, target, shared-cache and package-home paths in this new fixture. Never copy old fixture ownership markers or writable compiler state into a new study.

5. **Generate native-only seeds, then freeze actual inputs.** Initialize the fresh fixture and seed candidate before baseline:

   ```bash
   python3 -I -B "$BENCH_ROOT/work/benchmark/loader_fixture_delta.py" init \
     --name uv-loader-restack --template "$BENCH_ROOT/native-template.json" \
     --baseline "$BENCH_ROOT/artifacts/baseline/cargo" \
     --candidate "$BENCH_ROOT/artifacts/candidate/cargo" --copy-mode copy
   python3 -I -B "$BENCH_ROOT/work/benchmark/loader_fixture_delta.py" seed \
     --name uv-loader-restack --variant candidate
   python3 -I -B "$BENCH_ROOT/work/benchmark/loader_fixture_delta.py" seed \
     --name uv-loader-restack --variant baseline
   ```

   Each producer starts with empty owned target/shared state and runs exactly:

   ```text
   taskset -c 0-7 {canonical-cargo} -Zohm-defaults=yes test --no-run \
     --locked --offline -j 8 --message-format=json -v
   ```

   Review all native runlists and inventories before any check. Require successful native producers, no metadata-only crate compilation, every crate emit list containing `link`, no `Checking` phase and no test executable invocation. The recorded preparation has 733 crate compiler calls/artifacts and 92 built test executables per arm. Review the naturally generated 432 provenance entries per arm: baseline `loader_injected=true` with `[""]`, candidate `false` with `[]`. Do not manufacture those records. No `cargo check` or measured warmup is permitted before the fixed block.

   The actual excluded preparation restored baseline, candidate, candidate, baseline without running checks. It fixed the complete-pair reservation to 210 seconds using the original maximum pair command duration and observed maximum excluded restore duration. A fresh replication must record its own preparation facts and freeze its headroom policy before effects.

   The recorded active guard uses `maintenance_02.py` and exactly `applied-devbox-kube-proxy-reconcile`, `applied-devbox-azure-session` and `applied-devbox-teleport-reconcile`. It reads actual timer/service identities, preserves repeated `TimersMonotonic` entries and treats unavailable deadlines as wait-only. Missing services are not quiet admission. A different host policy must be declared prospectively; no service or timer is changed by this harness.

   Create new final protocol, host/tool identities, full SDK input rows, native snapshot hashes, entry/output paths and pending authority. Use the recorded `audit-tools/finalize_inputs_remote.py` and the JSON under `protocol/` as the binding reference, with actual new paths and identities. The final paired configuration must use `restack_control_02.py prepare --entry ...` as its prepare hook, rather than bypassing the pair-admission wrapper. Review the new source/input hashes and fresh output paths before approving that one execution. The original input/authority hashes describe only the recorded host.

6. **Run the one fixed block under the admitted wrapper.** The workload itself remains:

   ```text
   taskset -c 0-7 {canonical-cargo} -Zohm-defaults=yes check \
     --locked --offline -j 8 --message-format=json -v
   ```

   The twelve orders are `AB, BA, BA, BA, AB, BA, AB, BA, AB, BA, AB, AB`, with seed `2026102126`, zero warmup pairs and one command per variant in each pair. Launch the frozen wrapper against the newly bound files:

   ```bash
   python3 -I -B "$BENCH_ROOT/work/benchmark/restack_control_02.py" run \
     --inputs "$BENCH_ROOT/inputs.json" --inputs-sha256 "$INPUTS_SHA256" \
     --authority "$BENCH_ROOT/authority.approved.json" --authority-sha256 "$AUTHORITY_SHA256"
   ```

   Run it under a persistent task-owned supervisor with private file-backed stdin/stdout/stderr and an already-connected passive terminal notification. The included owner sources record the actual mechanism; an observer disconnect does not authorize another launch. Keep unrelated work off the host. Restore/verify before each sample, wait only before a complete pair, and keep all host checks outside the original native stopwatch. Any failed command, state/input mismatch or heavy-service-cycle failure invalidates the entire block. Preserve all raw data, restore the baseline native state and stop; no automatic replacement or extension is allowed.

   The modified `run_command` persists command, cwd, ordered-environment digest, exit, elapsed and raw-stream paths immediately after return, before fallible interpretation. All other collector/statistical functions remain AST-identical to the historical helper. The 59 recorded control tests cover the original restoration cases, raw receipt preservation, the timer parser and binding/refusal boundaries.

   After complete restoration, authenticate the raw gates from step 2 before reading effects. Retain all 24 samples, the original Cargo JSON/verbose streams, per-command raw receipts, service observations, restoration journal and exact source/tool/input records. Produce actual compiler/build-script counts only after those gates pass. A valid statistical miss closes this fixed replication.

The scope is one newly generated native seed per arm, restored across twelve pairs, with warm artifact pages and persistent private package-download bookkeeping. This is a whole-command first-check-after-test-build endpoint on one host. It does not measure cold storage, test-build wall time, PGO release binaries or a new SDK12 improvement. The historical Milan result and current Genoa result remain independently reported.

The public archive is a byte-preserved subset: complete current sample records, native seed logs/inventories, and build provenance. It excludes four large Cargo executable bodies and the private system-wide readiness capture; full original archive digests and member omission hashes remain in `privacy-and-selection.json`. Original absolute paths/hostnames and owned command PIDs are provenance, not transferable access. No private connection, control-plane, process-enumeration or credential material is included.
