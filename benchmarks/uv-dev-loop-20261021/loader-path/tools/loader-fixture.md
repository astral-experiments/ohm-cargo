# Native test build followed by check

The helper is work/benchmark/loader_fixture.py. It prepares an ordinary developer transition: complete cargo test --no-run, then run cargo check before any check artifacts have been produced. It never changes uv source or fabricates compiler provenance.

The uv root is a virtual workspace with members = ["crates/*"], no default-members, and no Linux build overrides in .cargo/config.toml. Unqualified commands therefore cover the whole workspace. The helper defaults to those commands. An optional --package uv narrows both seed and check symmetrically and is recorded as a different workload.

## Isolation and timing

Every named fixture lives directly under work/loader-fixtures/NAME and creates:

- bin/cargo: its own canonical executable, installed at the same physical path for both variants.
- live/target and live/shared: identical canonical target/build paths for both variants.
- package-home: a private copy of the original Cargo home's registry/git caches. Credentials, configuration, binaries, and the existing global cache database are not copied. This avoids modifying the current caches.
- snapshots/baseline and snapshots/candidate: separately produced native-only trees with original producer provenance.
- logs/seed-*.stdout, logs/seed-*.stderr, snapshot manifests, content inventories, and an append-only operation journal.
- paired.json: configuration for the existing paired runner.

The initialization template supplies the same compiler, job count, CPU affinity, flags, and package-cache input used for prior uv measurements. The helper replaces the active executable, target/shared paths, and Cargo home with its isolated paths. It freezes build-related environment values, explicitly leaves LD_LIBRARY_PATH unset, and rejects differing per-variant environments.

Each seed first deletes only its fixture's live tree, creates empty target/shared directories, installs the named producer at the canonical path, and runs the full native test build. The seed log must contain compiler-artifact messages and verbose rustc invocations whose emit lists contain link; metadata-only check invocations are rejected. There is no Cargo check warmup before the snapshot.

Before every measured check, including warmup pairs, the prepare hook replaces the whole live tree with that variant's native snapshot. It then verifies every file's content hash, size, mode, nanosecond mtime, symlink target, and hardlink relationship. Extra check artifacts from previous trials cannot survive. The paired runner starts timing only after this hook returns. Copying, checksum verification, and source/compiler validation are outside the measurement window.

The full checksum pass warms native-artifact pages consistently. This measures a first check following a native build with warm artifacts, not cold storage latency.

The snapshot owns separate inodes from live files; mutations during a check cannot alter its source snapshot. A single recursive cp -a invocation preserves hardlinks that span target and shared. The actual workspace filesystem rejected a tiny reflink probe on 2026-10-21, so this host uses cp -a --reflink=never. Reflinks are selected automatically where supported. Tar would still read/write the full data here, add an archive copy, and require explicit nanosecond timestamp handling; it is not currently used. Expect roughly two native snapshots plus one live tree, about 27 GB for the estimated 9 GB native state, plus the private package cache and check outputs.

Recursive deletion is restricted to the literal live child of a fixture created by this helper. An ownership marker, canonical path validation, a Linux mount-point check, and Python's symlink-resistant deletion guard every removal. Top-level symlink substitutions and nested mounts are rejected; symlinks inside the artifact tree are unlinked without following their targets. Existing snapshots cannot be overwritten.

Run the experiment serially. The helper locks seed/restore operations, but its lock does not span the timed subprocess; do not start another runner or manually restore the same fixture during an active paired run.

## Initial diagnostic pair

Run from the task workspace, after the candidate binary exists and the parent releases the build/benchmark slot. No commands below have been run on the real uv fixture by this agent.

    python3 work/benchmark/loader_fixture.py init \
      --name uv-loader-full \
      --template work/benchmark/check-path-cache-grouped.json \
      --candidate work/binaries/stripped/cargo-loader-path-v2

    python3 work/benchmark/loader_fixture.py seed \
      --name uv-loader-full --variant baseline

    python3 work/benchmark/loader_fixture.py seed \
      --name uv-loader-full --variant candidate

    python3 work/benchmark/paired.py run \
      --config work/loader-fixtures/uv-loader-full/paired.json \
      --output work/measurements/loader-native-only-pair-01 \
      --phase exploratory --pairs 1 --warmup-pairs 0 --seed 20261021

    python3 work/benchmark/loader_fixture.py verify \
      --name uv-loader-full \
      --results work/measurements/loader-native-only-pair-01

Initialization is light: it validates and hashes inputs and probes copying with a tiny file. The first seed performs the package-cache copy, then builds. Logs capture build progress without executing tests.

Before the diagnostic pair, inspect both snapshot manifests. Baseline native registry provenance should contain the previously observed empty relative loader entry and injection flag; candidate provenance should naturally record an empty directory list with injection false. Check counts and compiler runlists in the diagnostic report to establish that native dependency reuse actually occurred. The report also preserves non-rustc verbose `Running` commands, which show actual build-script executions. JSON `build-script-executed` records are listed separately because Cargo emits them when reusing cached script output too. A single pair establishes neither statistical significance nor a PR performance claim; it only checks the fixture and effect direction.

For another timing batch conditional on these native seeds, reuse the sealed snapshots with a new results directory and prespecified pair count/order seed. Every sample is restored to the same native-only state. Do not reuse the same results directory. Each restored check invocation is one timing observation, paired with the other variant; artifacts and compiler subprocesses are not independent samples. For independent confirmation of the build-to-check workflow, archive the completed fixture and initialize a fresh fixture under its original name, retaining the same absolute workspace, Cargo, target, shared-cache, and package-home paths. Produce fresh native seeds for both variants and reverse their seed order. Keep the archived manifests, snapshots, logs, journal, and completed validation report as evidence of the earlier batch. Replaying one pair of snapshots cannot establish that an incidental difference between those original seeds is reproducible.

## Evidence and limitations

The fixture manifest binds the uv git revision, tracked-file content/mode/mtime digest, compiler/input hashes, Cargo variant hashes, commands, build environment, and absolute paths. Snapshot manifests bind the successful seed logs and runlist, naturally captured loader provenance, and full native artifact inventory. Each preparation records the selected snapshot manifest hash, verified inventory hash, canonical paths, variant hash, and untimed restore duration. Verification joins these records one-to-one with paired samples and writes loader-fixture-validation.json.

The helper, paired runner, compiler inputs, and uv checkout must remain unchanged after initialization. A changed source mtime intentionally fails validation even when bytes are identical. Create a new fixture after changing the experiment implementation or inputs.

The private package cache persists across seed and check operations. Compiler artifacts, fingerprints, build-cache state, and incremental data under target/shared are restored; package-download bookkeeping is not reset. This follows a warm package-cache workflow and avoids unnecessary package extraction between samples.

Twelve small Python tests pass, covering snapshot immutability, cross-tree hardlinks, per-variant state at identical paths, content corruption despite preserved size/mtime, stale check removal, environment mismatch, ownership/path/mount guards, symlink escape safety, native-only runlist rejection, result validation, and the distinction between cached build-script output and actual script execution. These tests mock the Cargo subprocess and use tiny temporary files. The complete set passed after review on 2026-10-21 in 1.004 seconds. No Cargo build, uv seed, or benchmark has run as part of helper development.
