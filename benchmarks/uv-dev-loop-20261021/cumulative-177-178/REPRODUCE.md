# Reproducing the original composition

Verify SHA256SUMS, then extract raw-results.tar.gz into an otherwise empty
directory. RAW-MANIFEST.json binds its members. INPUTS.json maps recorded
input hashes to packaged files; runtime binaries and full attribution profiles
are external assets, explicitly identified by their hashes.

Use unmodified uv 3d82a6ad5a7eab8c68236553b7846517767c4b61 and the published
Ohm 1.99.0-6 compiler. Build the original PR175 baseline and candidate tree
4117e012ab1e082867dcb5a4b2a227e7f5200ff6 using the recorded common compiler,
flags, physical source and target paths. The build records and full source
patches preserve actual contents; the embedded Cargo commit deliberately
remains pinned 5e5d271d763d7beb38b48755e22bd59e93f02b97. These inputs predate the
later restack. Do not substitute current branch heads.

The strip helper assumes a workspace layout. To use its CLI, place it at
REPLICA/work/benchmark/strip_binaries.py, put linker outputs at
REPLICA/work/binaries/NAME, and create the matching
REPLICA/work/binaries/manifest.json entries with
original_linker_output_sha256. It writes work/binaries/stripped/NAME and its
section proof. Alternatively, apply objcopy --strip-debug to a separate
output file and compare allocated_sections before and after. Never strip or
dump sections into the only input copy.

For a different workspace prefix, copy each config and consistently relocate
all task-owned paths. Preserve the command, environment, source revision,
compiler, variants, workload and protocol. Supply your own ordinary-user
Cargo home, writable target/shared-cache paths, and local runtime tools.
Within every pair, both variants must use the exact same canonical executable
path and uv source/target paths. The frozen harness atomically installs the
variant's bytes at that canonical path before each sample. Do not invoke two
different Cargo paths or transplant warmed target directories from another
prefix. Seed and validate both variants at the new paths outside timing.

Use the frozen paired.py for Cargo-only instructions and paired_repeated.py
for native groups. The historical orchestration scripts are provenance records
with original absolute paths and seals; do not run them unchanged in a new
workspace. Recreate native preflights and execve checks, record all new input
hashes, and require fresh commands with no compiler/test children. Run outside
the sandbox that remaps root ownership, because that disables Ohm's trusted
shared registry cache. Keep the measurement host otherwise quiet.

Original fixed seeds are check/test IR 2026102141/2026102142 and check/test
native 2026102143/2026102144. Each has two warmup pairs. For example:

```sh
python3 paired.py run --config check-ir.json --output new-check-ir \
  --phase confirmation --pairs 12 --warmup-pairs 2 --seed 2026102141
python3 paired.py analyze new-check-ir \
  --confidence .99 --resamples 20000 --seed 1701
python3 paired_repeated.py run --config check-native.json --output new-check-native \
  --phase confirmation --pairs 30 --warmup-pairs 2 --seed 2026102143
python3 paired_repeated.py analyze new-check-native \
  --confidence .99 --resamples 20000 --seed 1701
```

The native config specifies eight repetitions and repeatable_workload=noop;
aggregate each group before paired analysis. Repeat the separate test workload
with --no-run and its declared seed. Retain warmups, failed attempts and every
raw subrun. Analyze only complete fixed batches and apply the full frozen
gate: at least 1% reduction, positive 99% lower bound, paired sign p ≤ .01,
and positive effects in both order groups. Report instruction and native
results separately. This procedure establishes a fresh-loop result only.
