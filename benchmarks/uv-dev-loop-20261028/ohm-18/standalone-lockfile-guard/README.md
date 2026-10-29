# Skip lockfile encoding for unambiguous package IDs

The baseline is Ohm -18 Cargo `7caf39914da1e28a67744ecbc963a5f26361474d`. The candidate changes nine lines in the collision check. Both are release-profile ThinLTO builds with the same unmodified standard library. All other Ohm components are the distributed -18 binaries. Each pair runs a full workspace `cargo check --locked --offline -j8` after an equal-length edit to the private Homebrew predicate in uv `c22e6b71933443e9cd299d4b6ac8de035ed4825b`. The two separately prepared checkouts use different edit literals and independently randomized orders.

| Cargo process and application threads | Base median | Candidate median | Paired saving | 99.22% median interval | Wins | Sign / order p |
|---|---:|---:|---:|---:|---:|---:|
| DynamoRIO | 961,369,618.5 | 959,827,198.0 | 0.159% | 0.040% to 0.232% | 8/8 | 0.00781 / 0.02857 |
| Cachegrind | 963,366,930.0 | 961,884,980.0 | 0.152% | 0.137% to 0.160% | 8/8 | 0.00781 / 0.02857 |

These counts cover the Cargo process and its application threads. A separate kernel exec trace confirms that the same unwrapped released rustc actually compiled uv. The clean and instrumented stock admissions and both drivers had identical compiler arguments and 696 matching metadata outputs per arm. The target was warm from checking this workspace, with no prior build-reuse marker. Cachegrind adds a loader preloader in the instrumented parent. The ordinary whole-command wall-time comparison of the same guard on the earlier patch stack was inconclusive on both checkouts. [Uninstrumented elapsed times](../resolver-wall/README.md) · [Observer audit](../observer-audit/README.md)

The existing `generate_lockfile::duplicate_entries_in_lockfile` integration test passed against both actual drivers. Nine CLI cases and 40 comparisons across lockfile versions 1–5 covered path, Git, same-name/version, multiple-version and diagnostic behavior. [Existing regression receipt](existing-cargo-regression.json) · [Original regression logs and exec traces](existing-cargo-regression.zip) · [Correctness cases](correctness.json) · [Ohm branch and PR overlap](ohm-overlap.md)

The [raw archive](raw-instructions.tar.zst) includes 32 original counter streams, both complete sample tables, source and build identities, observed execs, the 696-entry product manifests, stock controls and a standalone scorer. It was independently rescored after extraction with access to the original input roots denied. The optional 256,819,012-byte archive of the original metadata objects is identified separately. [All 32 rows](samples.csv) · [Archive identities and replay receipts](archive-identities.json)
