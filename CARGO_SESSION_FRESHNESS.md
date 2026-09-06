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
reads, and directory exclusion. Performance data will compare this branch with
its immediate parent using alternating source-edit measurements.
