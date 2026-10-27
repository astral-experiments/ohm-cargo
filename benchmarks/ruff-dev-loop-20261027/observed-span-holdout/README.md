# Cargo's foreign-span dependency receipt

These are native timings on a seven-package Rust workspace. One procedural macro reads a token’s foreign `Span` using stable `Debug`. A direct executable and an intermediate library observe it. A second executable consumes the intermediate constant, and a third calls an ordinary function. Both Cargo binaries use the same `x86_64-unknown-linux-gnu` release-PGO/BOLT compiler, at `27029b4bce40f3b5497add5019c02a11c16c4c18`. The measurements for the full Ruff workspace are separate.

| Whole native build command | Control median | Candidate median | Median paired change | Pairs with faster candidate |
| --- | ---: | ---: | ---: | ---: |
| No source edit | 184.803 ms | 97.674 ms | 47.59% faster | 12/12 |
| First build after the one-byte source edit | 344.183 ms | 472.417 ms | **36.50% slower** | 0/12 |

The elapsed-time measurement covers the whole offline `cargo +ohm build` for the three terminal packages, including the affinity and mount-namespace launcher. Both arms see the same logical paths. Their source trees, Cargo homes, build directories and targets are separate. The 12 genuine edits alternate adding and removing one ASCII byte from the documentation for a private function. Every pair took part in the analysis.

The prespecified primary is the no-op build. Its paired reduction is the median of the 12 individual `100 × (1 − candidate / control)` values. The third and tenth ordered reductions give the registered distribution-free interval, 44.60% to 48.98% lower. The one-sided exact test used the mean paired log ratio over all 924 balanced allocations of six control-first blocks; its p-value is 1/924 (0.001082). The same paired reduction formula yields −36.50% on genuine edits. The edited endpoint was prespecified as descriptive. Each individual command median in the table is the median of its own arm's 12 observations.

On every unchanged traced replay the control ran two full rustcs and one link-only rustc, including two final linker processes. The trained candidate ran zero. On every real edit, both arms ran four full compilers, one link-only compiler and three final linkers. Candidate Cargo collected binary dep-info on the two actual observers. All three native executable SHA-256s and printed observations matched their independent empty-target references on all 48 timed commands and 48 separately traced replays. A one-byte shift changes both observed ranges. The ordinary executable’s output and ELF digest are stable in both directions.

## What Cargo verifies

When writing an observer receipt, candidate Cargo appends `OBS1`, the index of rustc’s deliberately missing `ohm-foreign-span-bytes` prerequisite, and its incomplete/complete byte. It hashes the entire serialized dep-info up to and including those fields with **BLAKE3**, then appends the 32-byte digest. Parsing validates the marker and index, recomputes BLAKE3 over the preceding bytes and checks the stored digest before accepting the status. This is an unkeyed integrity check on trusted local build artifacts. A writer that controls an entire artifact can compute a new digest.

`command-records.jsonl` publishes the captured index, complete bit, stored BLAKE3 and dep-info file size and SHA-256. The full dep-info body can contain environment strings and stays private. The offline verifier checks the published trailer fields, actual behavior and process evidence. SHA-256 identifies the dataset files and verifies native executable byte equality. Cargo’s receipt validator uses BLAKE3.

## Input-read cost

The read attribution was a separate, untimed diagnosis on preceding compiler `4e967d262ea9dae4c1e673ec2e1d07a7dc492d8bca2ea42bb90cbcd509da9c7c`, with the same two Cargo binaries. On a candidate no-op, Cargo read 98,902,551 installed SDK bytes. In each edit direction, Cargo read 187,964,474 SDK bytes and the two observing compilers read 88,319,067 and 98,902,551 SDK bytes. On this fixture the observed inputs include substantial installed standard-library metadata and archives. The counters cover bytes returned by `read` and `pread64` on `.rmeta`, `.rlib` and `.so` inputs. Memory-mapped access is outside the count. Both arms and both directions are included in `process-reads.csv` and `library-reads.csv`. In a subsequent run using the streaming reproduction, Cargo read 140,324,731 SDK bytes in each genuine edit. Its no-op and both observing compilers reproduced their original SDK counts exactly. `streaming-replication-reads.csv` keeps these six unscored controls separate from the original observations.

## Verify and reproduce

```sh
sha256sum -c SHA256SUMS
python3 -B verify.py
```

`native.csv` is the original 48-row native timing export. `command-records.jsonl` retains all 114 command outcomes, source digests, observer states and native products. `successful-execs.csv` contains all 798 successful `execve` records from 66 untimed invocations. The table preserves execution order, anonymous per-invocation process identities, executable classes, crate names, compiler mode and the two relevant flags. Each execution record agrees with the original harness’s independently emitted roster and image list. Four fixture observations plus one initial training invocation also contained an unnamed, unfinished syscall with no return value. `trace-quality.json` lists those five records separately. Only an `execve` with a returned success is counted. Every runtime observation and process class in the scored pairs can be checked offline.

To run the native study on Linux, use a Rustup proxy named `cargo`, a matching SDK in `STATE/sysroot`, the matching Rustup home and `ohm` alias in `STATE/rustup`, GNU tools, bubblewrap, strace, and four available CPU cores. The public runner uses the original timed command, training and fixed schedule. Its SDK path is a required argument. Supply the exact subject binaries listed in `subjects.json`. The candidate Cargo source is included as a patch against `d577be8eb1db7a3a4e4a82246d64644aaf3e0bff`. The working path must be new.

```sh
python3 -B reproduce.py --mode score --state "$STATE" --driver "$DRIVER" \
  --parent "$CONTROL_CARGO" --candidate "$CANDIDATE_CARGO" \
  --work /dev/shm/cargo-observer-native --cpus 0-3
```

For the input-read diagnosis, run `diagnose.py` with the same parameters and a different new working path. Supply the preceding driver listed above to replicate the recorded cost attribution. It streams the per-process syscall information to `aggregate_reads.py` through a pipe. The resulting `read-activity.csv` files contain only process classes, allowlisted library basenames and numeric byte counts. The same filter reproduced every per-file aggregate for all six saved diagnostic commands. The public files contain curated command/ELF evidence and count projections, with the source fixture and fixed scheduling plan.
