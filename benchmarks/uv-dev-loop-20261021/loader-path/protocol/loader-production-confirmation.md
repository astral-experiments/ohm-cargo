# Independent loader production-settings validation

The fixed design is `loader-production-confirmation-protocol.json`: 12 balanced
randomized pairs, seed 2026102126, no measurement warmups, one first check per
restored native state. Wall time is primary; CPU seconds and compiler invocation
counts are secondary. Require the 99% paired-bootstrap interval to exclude no
improvement, exact sign-test p <= 0.01, at least 1% geometric wall reduction, and
positive effects in both orders. Retain all samples and inspect no interim effects.
The earlier normal-build one-pair diagnostic is never pooled into this validation.

Use the matched all-static/ThinLTO/one-codegen-unit/dev-channel Cargo builds atop
PR175, with only the frozen loader-v2 patch differing. These builds have no PGO
and use stock Rust 1.99.0; describe them as production settings, not identical to
the published release. Both compiler invocation source trees and all binary,
patch, build provenance, runtime library, CA bundle, helper, and configuration
hashes must be recorded before seeding. The uv source and Ohm rustc remain pinned.

Once both real production binaries are frozen, lock the existing marked fixture,
verify its completed diagnostic evidence, and rename it atomically to
`uv-loader-pr175-diagnostic-01-archive`. Retain its complete original contents;
the archived marker deliberately retains the historical original path, so do
not invoke a mutating helper on it under the archive name. Initialize a new
`uv-loader-pr175` fixture at exactly the original canonical paths, with the real
production pair and the separate `loader_fixture_delta.py` helper. Create fresh
empty target/shared trees for each producer, in candidate then baseline order.
The private package cache starts as a new copy of the same public input cache.
Both commands are full-workspace `cargo test --no-run`; no tests execute.

Seal and inspect both native snapshots and runlists before measurement. There
must be no metadata-only check compilation in either producer. Compare natural
loader provenance without editing it. Record the quiet host, ownership, source,
and frozen input identities again. The statistical sample is a restored-state
pair conditional on one newly generated native seed per variant; it is not a
set of twelve independently rebuilt native seeds.

The delta helper uses local rsync with checksums, archive semantics, hardlink
preservation, deletion of extra entries, and nanosecond mtime comparison. It
uses neither inplace writes nor links into snapshots. Before changing inode
metadata it detects hardlinks outside the disposable live tree and instead
uses the original independent full-copy restore. After rsync it requires the
full sealed content/mode/ns-mtime/symlink/hardlink inventory; surplus hardlinks
or any other mismatch trigger an independent full copy and full verification.
A failed full verification prevents timing. Every fallback is retained in the
journal. All deletion, copy, rsync and hashing operations finish before timing;
no restore runs concurrently with any measured command.

Each unique inode is hashed once per inventory; all per-path rows are retained.
Inode identity, size, mtime, ctime, mode, and link count are checked for changes.
The original full-hash inventory returns identical rows on the hardlink fixture.
The original 12 tests plus 19 delta tests passed locally and on host4, including
same-size/mtime corruption, outside hardlinks, file/directory symlink escapes,
surplus internal hardlinks, source tampering and changes during hashing.
The original helper remains unchanged. On the diagnostic seeds, 7.59 GB of
13.67 GB unique bytes had matching content and paths across variants, so delta
restoration can avoid substantial writes; its speed is not part of the claim.

Run the frozen paired harness with `--phase confirmation --pairs 12
--warmup-pairs 0 --seed 2026102126`, then the new helper's `verify`, then the
frozen analysis with `--confidence 0.99 --resamples 20000 --seed 1701
--minimum-pairs 12 --minimum-improvement 0.01`. Preserve the raw logs, snapshot
inventories/runlists, per-sample restore details, analysis, and hashes. Transfer
small evidence only; retain full native snapshot trees on host4.
