# Ruff #286 replication with two newly compiled Cargo binaries

Both Cargo executables were built from the pinned Git sources on one machine, using the published source builder, the installed Ohm 1.99.0-18 compiler and 523 registry archives verified against the Cargo source lockfile. The parent was `2fe90823d…`, the candidate was `97e5acfb7…`, and both reported the same complete `cargo -Vv`. Their new standard release binaries had SHA-256s `dbda53099e3dcb06caf1ed3a8618033407b9a6cf682e49d5d9dad170f9f98747` and `eb5e54c9e412a68aa423400ca1fb48307cdfa1c14e2e2250ee8de285aa1f3fcd`. One executable was then installed at the same logical SDK path in each runner view. [Source-based reproduction instructions](../rc20-profile-workspace-resolve-local-rerun/README.md) · [parent source](https://github.com/astral-sh/ohm-cargo/tree/2fe90823d8eadc95de56c2cde8d41e0082aac0eb) · [candidate source](https://github.com/astral-sh/ohm-cargo/tree/97e5acfb7b8eefde1ce07d703fc4849d6d36e37c)

## Native build and workload checks

Each clean Cargo build emitted 383 typed artifacts. All 383 compiler invocations across the two builds had literally matching argument vectors, including extern paths. The actual compiler SHA-256 was `c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60` in both. The source-building command includes `-Zohm-defaults=no`. Each arm invoked the shipped LLD through its driver 49 times and the system linker once. The two kernel trace readers recorded the same process counts and tool hashes. The kernel trace records the compiler's produced linker arguments as well; temporary paths can differ between link invocations. [Build receipt](build-receipt.json) · [source build and native calls](source-build.json) · [independent trace reader output](independent-build.json)

The Ruff commands used ordinary `cargo +ohm` with the newly built host Cargo. The edit reversed or restored only the three inactive `[profile.fast-test]` lines from Ruff `6dc1031889aa` against `93526150df07`. The lockfile remained byte-identical. The two package warmups each ran one compiler and produced a Rust library. The two serde warmups each ran 15 compilers and six instances of the installed, unmodified Wild, SHA-256 `0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5`. Each following native edit and repeat check showed zero compiler and zero linker invocations. The external Rust consumer printed `17 29 12`. Each serde binary passed `invalid_range_deserialization`, `range_serialization` and `size_serialization`. Every A/B view of the same warmup had identical declared files and complete executable hashes. The independently seeded logging and timing namespaces have different path-bearing binaries; the exact per-namespace hashes are recorded. [Native linker path and argument evidence](ruff-linked.json) · [per-command data and executable hashes](source-run.json)

The separate resolver-log qualification had four genuine full resolutions for the parent after each workload's profile edits and four cache hits for the candidate. The very first candidate training is outside this comparison. Across both workloads the complete example contains 64 native controls and 256 untraced ordinary timing processes, with 32 adjacent pairs per selection. Both source-build and workload stages used the same four CPUs. The source build’s available memory stayed above 26 GiB, with caps set at 16 GiB of available memory and 45/40 GiB free on the two physical filesystems.

## Local wall results

| Selection and phase | Parent median | Candidate median | Paired median reduction | 95% interval | Faster pairs |
|---|---:|---:|---:|---:|---:|
| Package build after edit | 186.56 ms | 65.50 ms | 64.91% | 64.57% to 65.17% | 32/32 |
| Package, first unchanged repeat | 64.53 ms | 64.96 ms | −0.74% | −1.64% to 0.34% | 14/32 |
| Package, edit and repeat | 251.75 ms | 130.61 ms | 47.96% | 47.30% to 48.43% | 32/32 |
| Serde test build after edit | 199.26 ms | 75.42 ms | 62.08% | 61.78% to 62.48% | 32/32 |
| Serde, first unchanged repeat | 75.29 ms | 75.37 ms | 0.38% | −0.66% to 1.08% | 19/32 |
| Serde, edit and repeat | 274.73 ms | 151.53 ms | 45.53% | 44.56% to 45.75% | 32/32 |

These clocks form one local standard-release replication. The original H8 release-PGO results and the separate supplied-PGO local run each retain their own measurements. The interval uses 20,000 paired resamples stratified by edit direction and arm order. Both edited sign tests have two-sided P approximately 4.66 × 10⁻¹⁰. The unchanged intervals include zero. [Original H8 cohort](../rc20-profile-workspace-resolve-wall/README.md) · [local supplied-binary cohort](../rc20-profile-workspace-resolve-local-rerun/README.md)

## Reproduce

Use the full checkout and offline cache instructions in the sibling tutorial. Export this component from the same evidence branch beside both directories named in that tutorial. The initial `git archive` can take all three component paths. In that recipe use `--workload both`. To emit comparable source-build process evidence, run its two final operations as shown below with the same `ROOT`, `REPRO`, `SDK` and `CPUS` variables. Choose new output names. Here `REPRO` names the sibling local-rerun directory. The only traced commands in these instructions are the Cargo source bootstrap and the runner's off-clock controls.

```bash
EXAMPLE="$(dirname "$REPRO")/rc20-profile-workspace-resolve-local-source-build"
(cd "$EXAMPLE" && sha256sum -c SHA256SUMS && python3 -IB verify.py)

strace -f -qq -s 131072 -e trace=execve,execveat -o "$ROOT/source-build.exec" -- \
  python3 -IB "$REPRO/build_pair.py" --cargo-checkout "$ROOT/ohm-cargo" \
  --out "$ROOT/new-source-builds" --jobs 4
python3 -IB "$EXAMPLE/audit_build.py" --builds "$ROOT/new-source-builds" \
  --trace "$ROOT/source-build.exec" --sdk "$SDK" > "$ROOT/source-build-audit.json"

python3 -IB "$REPRO/run.py" --checkout "$ROOT/ruff" --sdk "$SDK" \
  --control "$ROOT/new-source-builds/A/cargo" --candidate "$ROOT/new-source-builds/B/cargo" \
  --pair-receipt "$ROOT/new-source-builds/build-receipt.json" \
  --cargo-home "$ROOT/offline-ruff" --cpus "$CPUS" --workload both \
  --scratch "$ROOT/source-run-scratch" --out "$ROOT/source-run-results"
python3 -IB "$EXAMPLE/public_report.py" "$ROOT/source-run-results" > "$ROOT/source-run.json"
python3 -IB "$EXAMPLE/check-ruff-linker.py" "$ROOT/source-run-results" "$SDK" > "$ROOT/ruff-linked.json"
```

The example staged the 523 archive inputs locally and added `--offline` to the Cargo source builds. The public source and runner machinery were executed unchanged. The package source trees, registry archive cache, source build and measurement output roots were all private to the run. The original kernel exec stream and stdout/stderr/indexes are retained by the runner and can contain host paths on a reviewer’s machine. Cargo prints its absolute test executable in the second stderr line of each ordinary serde command. The public projector checked all 128 such paths against the actual typed target and replaced only the private workspace prefix. The original stream SHA-256 and the exact remaining text are retained for every visit. Package-build streams were exported literally. The unmodified sibling reporter remains available for local private analysis. This packet also includes literal argument and raw-trace digests, role and source identities, and executable hashes. Run `python3 -IB verify.py` to recompute effects, compare the independent source-build readers, and reject six corrupted examples.
