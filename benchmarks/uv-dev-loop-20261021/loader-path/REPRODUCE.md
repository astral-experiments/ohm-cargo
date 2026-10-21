# Verify and reproduce the loader-path experiment

Use the files at this evidence commit as immutable inputs. The code patch and benchmark evidence are separate branches so the code review contains only the three-file compiler/test change.

1. **Verify the preserved evidence.** From this directory, run `python3 verify.py`. It checks the publication file manifest, both compressed archives, and every decompressed member against its external SHA256/size manifest, without invoking Cargo or executing archived scripts. To also extract into a new empty directory, run `python3 verify.py --extract /absolute/new/evidence-copy`. Extraction creates `production-confirmation/` and `normal-build-n1-diagnostic/`. The 250 MB and 92 MB raw collections remain separate. The original outer seals are retained both inside the archives and under `original-manifests/`; compression changes no member bytes.

2. **Replay the statistics without building.** Copy the production result's `manifest.json` and `samples.json` into a new analysis directory, then run the exact frozen analyzer. Do not point it at the sealed originals because it writes `analysis.json`.

   ```bash
   mkdir /absolute/new/analysis-copy
   cp confirmation/manifest.json confirmation/samples.json /absolute/new/analysis-copy/
   python3 tools/paired.py analyze /absolute/new/analysis-copy \
     --confidence 0.99 --resamples 20000 --seed 1701 \
     --minimum-pairs 12 --minimum-improvement 0.01
   cmp confirmation/analysis.json /absolute/new/analysis-copy/analysis.json
   ```

   The primary effect is the geometric mean of the 12 paired baseline/candidate wall-time ratios. Bootstrap resampling uses whole pairs, not subprocesses or artifacts. The frozen acceptance conditions require at least 12 pairs, at least 1% reduction, a 99% speedup interval wholly above 1, exact two-sided sign p ≤ .01, and gains in both AB and BA groups. All 24 measurements are retained. The historical analyzer calls this common gate `screen`; the manifest and prespecified protocol identify this batch as confirmation. Secondary CPU statistics use the same pairs. The raw verbose invocation audit and `loader-mechanism.json` separately establish the compiler counts.

3. **Rebuild the matched Cargo pair if the original binaries are unavailable.** Use a new disposable checkout of `astral-sh/ohm-cargo`, a private build target and package home, and stock Rust 1.99.0. Build each variant serially at the **same physical source and target paths**, preserving Git HEAD `5e5d271d763d7beb38b48755e22bd59e93f02b97` in both. Apply `build/pr175.patch` to produce the baseline; apply it plus `build/loader-path-v2-final.patch` to produce the candidate. Do not commit these patches before building: the measured binaries intentionally share the original embedded Cargo commit, while their actual source trees differ. The code-review branch is based directly on PR175 and has the same candidate tree.

   Verify each complete source tree with a temporary Git index before compiling. Expected baseline: `3d67bfb965bc0b6452ab78205045c5154db0acf7`; expected candidate: `fce366b238ace1b2021808769d857aa56eadcd56`. The exact build command was:

   ```text
   /home/dev-user/.rustup/toolchains/1.99.0-x86_64-unknown-linux-gnu/bin/cargo \
     build --release --locked --bin cargo --features all-static,ohm-defaults -j 8 -v
   ```

   Reproduce all environment settings and clear the environment names listed in `build/provenance-pr175.json` and `build/provenance-pr175-loader-v2.json`. Key settings are `CARGO_INCREMENTAL=0`, `CARGO_PROFILE_RELEASE_LTO=thin`, `CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1`, `CARGO_PROFILE_RELEASE_DEBUG=1`, `CARGO_PROFILE_RELEASE_OPT_LEVEL=3`, `CARGO_PROFILE_RELEASE_INCREMENTAL=false`, `CARGO_PROFILE_RELEASE_STRIP=none`, `CFG_RELEASE_CHANNEL=dev`, `LIBZ_SYS_STATIC=1`, and explicit normal SSL certificate paths. No PGO flags or profile are present. Record inherited Cargo configuration and native build environment as the original provenance did. Use identical compiler, linker, features, configuration, and environment for both variants. Preserve each full linker binary before the next build; create separate `objcopy --strip-debug` copies and verify every allocated ELF section remains identical using `build/historical-tools/strip_binaries.py`'s `allocated_sections` function. The recorded `.build.json` and `.strip.json` files bind the full and measured stripped binaries.

   Historical build drivers are included for exact audit, but contain the original task paths and prerequisites for earlier build batches. They are not standalone setup commands. A new build should record its own provenance and hashes; matching source and flags does not promise byte-identical binaries across changed build paths or toolchain inputs.

4. **Create an isolated uv benchmark root.** Use Linux with Python 3, Git, GNU `cp`, `rsync`, `taskset`, the linker/native dependencies needed by uv, and sufficient space for two approximately 16.4 GB logical native trees, one live tree, a private package cache, and check outputs. Prepare a clean uv checkout at `3d82a6ad5a7eab8c68236553b7846517767c4b61`, the Ohm 1.99.0-6 compiler distribution, the two real Cargo binaries, and a public-registry/Git package cache sufficient for offline builds. Do not copy credentials or user configuration. The original Ohm archive SHA256 is `98a4f4f99ea1ff36e10209258724426496afbbcab14d746294fe53a2fedad37c`; verify rustc and driver hashes in the README. The uv lockfile SHA256 is `747296375bb1889689f3bbb1e0303bddd071d6a65117c00be50856448260d014`.

   Place the frozen Python helpers under `BENCH_ROOT/work/benchmark/`, retaining their relative layout. `loader_fixture_delta.py` derives its fixture base from that location. Use a new template based on `protocol/loader-pr175-production-template.json`; adapt absolute paths consistently, keep variant environments identical, and retain the same command/flags. Include both binaries' build/strip/provenance metadata, actual patches, compiler/driver/lockfile, the frozen helper/protocol, resolved runtime libraries, and CA bundle in `record_files`. `CARGO_HOME` in the template points to the input package cache; initialization replaces it with a separate private copy containing only `registry/` and `git/`. Record any deliberate differences as a new experiment.

   The original benchmark root was `/tmp/ohm-hillclimb-20261021/confirmation-path-cache`; fixture name `uv-loader-pr175`. Its canonical Cargo, target, shared-cache, and package-home paths are in the frozen protocol. A rerun may use a different isolated root, but **both variants must share the same absolute live paths within that rerun**. Never reuse or rewrite the archived fixture markers, whose hashes, source mtimes, and ownership paths describe the historical run. Seed new trees instead. Keep LD/DYLD/preload/audit paths unset, as specified in the template; explicit empty values are a different workload.

5. **Freeze the new protocol and seed native artifacts.** Retain the 12-pair design, no measurement warmups, seed `2026102126`, one check per variant per pair, and candidate-then-baseline producer order. Finalize all actual inputs before initialization. Use the helper's `init` operation with the real binaries, then seed both variants serially:

   ```bash
   python3 "$BENCH_ROOT/work/benchmark/loader_fixture_delta.py" init \
     --name uv-loader-pr175 --template "$BENCH_ROOT/production-template.json" \
     --baseline "$BENCH_ROOT/binaries/cargo-pr175" \
     --candidate "$BENCH_ROOT/binaries/cargo-pr175-loader-v2" --copy-mode copy
   python3 "$BENCH_ROOT/work/benchmark/loader_fixture_delta.py" seed \
     --name uv-loader-pr175 --variant candidate
   python3 "$BENCH_ROOT/work/benchmark/loader_fixture_delta.py" seed \
     --name uv-loader-pr175 --variant baseline
   ```

   Each seed starts with empty fixture-owned target/shared trees and runs the ordinary full-workspace command below. The uv root has no `default-members`, so the unqualified commands cover the full workspace. No uv files are modified, no check artifacts are fabricated, and no test executable runs.

   ```text
   taskset -c 0-7 {canonical-cargo} -Zohm-defaults=yes test --no-run \
     --locked --offline -j 8 --message-format=json -v
   ```

   Before timing, inspect both snapshot manifests/runlists and the journal. Require successful seeds, zero metadata-only crate compilations, all crate emit lists containing `link`, no check before seed review, and no test executable in other invocation records. In the recorded seeds each variant had 733 crate rustc invocations, 56 build-script invocations, and 92 built test executables. Review naturally produced provenance: baseline had 432 entries with `loader_injected=true` and `compiler_search_directories=[""]`; candidate had 432 with `false` and `[]`. Do not edit provenance to force these counts. The archives retain exact runlists, inventories, logs and seed-review code/results.

6. **Run one uninterrupted fixed batch.** Ensure no competing build/profiler/benchmark is using the host. Do not run producers, restore copies, or another runner concurrently. The helper locks restore operations, but the lock deliberately does not span the timed command. It verifies frozen source content, mode and mtime as well as recorded binary/runtime inputs. Each prepare hook restores the selected native snapshot, removes previous check outputs, verifies exact contents/modes/ns-mtimes/symlinks/hardlink relationships, and only then returns to the timer.

   ```bash
   python3 "$BENCH_ROOT/work/benchmark/paired.py" run \
     --config "$BENCH_ROOT/work/loader-fixtures/uv-loader-pr175/paired.json" \
     --output "$BENCH_ROOT/results/loader-confirmation" \
     --phase confirmation --pairs 12 --warmup-pairs 0 --seed 2026102126
   python3 "$BENCH_ROOT/work/benchmark/loader_fixture_delta.py" verify \
     --name uv-loader-pr175 --results "$BENCH_ROOT/results/loader-confirmation"
   python3 "$BENCH_ROOT/work/benchmark/paired.py" analyze \
     "$BENCH_ROOT/results/loader-confirmation" \
     --confidence 0.99 --resamples 20000 --seed 1701 \
     --minimum-pairs 12 --minimum-improvement 0.01
   ```

   The measured command is `taskset -c 0-7 {canonical-cargo} -Zohm-defaults=yes check --locked --offline -j 8 --message-format=json -v`. Retain every sample and failure, inspect no interim effects, and do not extend or stop the batch based on the effect. Failed commands or state/input integrity failures invalidate the batch and must remain recorded. Check exact join coverage between preparation records and measured samples, verify no test executables ran, and produce the compiler-count summary only after completion.

The helper uses checksum rsync without inplace writes or hardlinks into snapshots. It rejects unsafe paths/mounts and detects external hardlinks before changing inode metadata. Any mismatch falls back to a full independent copy and full verification; a failed final check prevents timing. All copying and hashing are excluded from measured wall/CPU time. Every original production restoration used rsync successfully without fallback. Native trees and binaries are intentionally omitted from Git; their exact inventories and identities are included, and the original full trees were retained in the task-owned host4 fixture. Reconstructing them requires the seed steps above.

For interpretation, keep the original limits: one new native seed per variant, warm artifact pages after hashing, a persistent private package-download cache, one Linux host, no PGO, and stock rather than release-bootstrap compiler. Additional independently generated seed pairs or release-PGO builds would be separate validation, not extra samples appended to this frozen run.
