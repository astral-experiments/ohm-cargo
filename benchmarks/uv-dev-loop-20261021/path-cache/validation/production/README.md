# Historical PR175 path-cache production CLI validation

On `charlie-oss-4`, the exact production-settings path-cache binary passed all 97 preexisting `build_dir` cases: **93 passed, 4 ignored, 0 failed**. This is correctness evidence for the historical PR175 candidate, not a new performance comparison or validation of a later restack.

- Candidate SHA256: `c060facdbaae756453968d6eaef1c5ab71c127d15c329a8453e260ef3064c583`.
- Candidate source tree: `b0dfb3fe2cfd8d310efa04a345f58886296f712a`, PR175 atop pinned Cargo `5e5d271d763d7beb38b48755e22bd59e93f02b97`.
- Unmodified prebuilt integration runner SHA256: `6415ee68be80518f701a6e4d0b45c1ef76bab599af203625f06b7fa4ac696182`, compiled from tree `c692e3c07d295e596b9f10eb4b1c89bb498caf68`.
- Test attempt: 2026-10-21 11:43:07–11:44:49 UTC. All cases ran serially. No test or Cargo source was edited or rebuilt.

The runner's compiled-in absolute executable and scratch paths required a new task-owned workspace at `/home/dev-user/Documents/Codex/2026-10-20/i-want-you-to-hillclimb-on` on host4. Every parent was absent and created exclusively; ownership is recorded. The validation uses ordinary UID/GID 1000 with the host identity mapping, no symlink or namespace. Binaries, metadata, and evidence live separately under `/tmp/ohm-hillclimb-20261021/path-cache-validation`. Completed loader and SBOM fixtures were not used as test scratch.

The launcher supplies the supported classic-default compatibility setting when the test leaves `__CARGO_OHM_DEFAULTS` unset. It preserves explicit test `yes`/`no` values and explicit nightly channel selection. It restores the actual dev channel only for inherited stable/beta/unset values, because the stable override otherwise suppresses the inherited Ohm setting. Published Ohm `bin` is on `PATH`, `RUSTUP_TOOLCHAIN` and wrappers/flags are cleared, and `LD_LIBRARY_PATH` explicitly names that release's `lib`. That last setting avoids the separately diagnosed preexisting empty-loader-path provenance issue. The complete launcher, environment, compiler/driver/runtime hashes, actual command, and before/after binary hashes are in `evidence/attempt-candidate/report.json`; `cli-execve.log` proves that the launcher executes the frozen candidate.

The case list matches the historical 93-pass/4-ignored run exactly. The three loader-v2 additions are excluded from scope and are absent from this runner's 97-case `build_dir` listing. No unexpected failures required a matched-baseline diagnostic.

The source archive is the runner's recorded Git tree. After the run, all 3,096 tracked entries were verified against its extraction. All regular file bytes and executable bits match exactly. Python's safe tar filter removes trailing slashes from 23 unrelated `cargo_add`/`cargo_remove` fixture symlink strings; their destinations are identical, and every normalization is recorded. An initial collection check rejected those textual differences; that collection-only attempt is retained separately. The passing test attempt was never rerun or changed.

Evidence identities:

- `production-path-cache-correctness.tar`: `3a297338437f95eafcf09b25806735899549d32aee2b5c6a7831e935ec3f9ef4`.
- `evidence/attempt-candidate/report.json`: `6522d23492491ca932f99217d271191a4b8458ea8eca48cbdaa77e21f265f17b`.
- `evidence/attempt-candidate/tests.log`: `f5d7c546677fc97a4640fae691998947550045fe0e157588b3c71dd8fa987b36`.
- `evidence/evidence-manifest.json` binds all 18 small package files and the omitted immutable binary/source-archive identities. The full binaries and source archive remain retained locally and remotely.

To reproduce, use the same runner and frozen production candidate, recreate its otherwise-unused baked paths in an isolated ordinary-user environment, and follow the recorded launcher/environment and exact 97 names in `tests.json`. Run `run_remote.py candidate` only in a new attempt root; it intentionally refuses to overwrite an earlier attempt. The helper checks all input hashes, records runtime identities, verifies the compiled-in CLI with `strace`, runs the fixed list, and checks the immutable binary/runtime hashes again afterward.
