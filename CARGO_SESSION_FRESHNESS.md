# Retained per-unit freshness

A prepared session retains immutable results for ordinary metadata check library
units whose entire dependency closure has the same contract. Each request still
creates a new `BuildRunner`, new dependency edges, new mutable fingerprints, new
jobs, and new locks. Normal warning replay, JSON artifact messages, source
verification, and compilation remain in Cargo's existing execution path.

The cache records values at the reads that originally established a Fresh
fingerprint: Cargo dep-info bytes, the short fingerprint bytes, source and
reference mtimes, output mtimes, and any package-root canonicalization required
by parent-relative dep-info paths. An mtime served from a request-local cache
must agree with the regular-file metadata before admission. Repeated conflicting
reads reject admission. Capturing an independent snapshot after deciding Fresh
would incorrectly admit a racing change that the decision never consumed.

On a later request, the cache checks every saved observation against the
filesystem and validates dependency versions before reconstructing a result.
A changed, missing, unreadable, or unsupported input falls back to normal
fingerprinting and gives the unit a new version, invalidating retained ancestors.
All dependency edges participate in eligibility and version checking, including
edges ordinary fingerprint hashing can omit. Read sets preserve logical paths.
Directories, checksum freshness, worktree seed state, and dependency closures
containing build scripts or proc macros are not admitted. Opaque preparation
inputs and `mtime-on-use` disable this cache for the request.

This removes repeated dep-info parsing, static fingerprint construction, and
freshness comparison work for unchanged units. It still polls saved file inputs
and schedules Cargo's normal fresh jobs; its cost is not independent of graph
size. Compiler errors and incomplete calculations cannot publish new entries.

Validation covers real transitive includes, deletion and error recovery, output
mtime regression and deletion, interrupted short fingerprints with preserved
mtime, corrupt dep-info, warning replay, and JSON artifact freshness. Focused
read-set tests cover racing values, request-local mtime cache values, conflicting
reads, and directory exclusion. The release build, 24 session unit tests, and
41 session integration tests pass.

## Measurements

Thirty alternating parent/current pairs after actual leaf edits in a 101-crate
Linux x86_64 workspace produced these medians:

| Compiler | Parent client | Cached client | Parent server | Cached server | Client speedup |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ohm 1.98.0-2 | 114.22 ms | 115.12 ms | 105.03 ms | 106.09 ms | 0.992x |
| Stable Rust 1.97.1 | 107.72 ms | 104.70 ms | 96.83 ms | 95.26 ms | 1.029x |

These results do not establish a substantial performance improvement. The Ohm
median regressed slightly; the stable median improved slightly. Validation still
polls the saved inputs, and every request still constructs mutable fingerprints
and schedules every unit. Removing dep-info parsing and static fingerprint work
does not remove that remaining work. Individual samples include substantial
host noise; no outliers were removed.

Both sides retained one preparation across 31 checks, and every measured edit
changed the leaf dep-info output. Cold preparation and startup are reported
separately. The immediate parent is the input-watcher branch at `2fbb8db`; the
measured implementation is `2445ce8`. Shared Cargo build-script outputs can retain
an earlier embedded commit string, so the data records each executable SHA-256
as its measured binary identity.

Reproduce with `benches/session_compare.py --before PARENT_CARGO --after CARGO
--crates 100 --rounds 30`, selecting the compiler with `RUSTUP_TOOLCHAIN`.
[Ohm samples](benches/session/results/freshness-ohm-linux-x86_64.json) and
[stable samples](benches/session/results/freshness-stable-linux-x86_64.json) include
every measurement, compiler identity, executable hash, and session counter.
