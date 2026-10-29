# Ohm resolver duplication check

The 2026-10-29T02:34:58.245628+00:00 census covered 55 published Ohm releases, 286 Cargo branch heads and all 230 Cargo pull request heads, including 143 open PRs. The 318 unique commits included 305 with Cargo source and 13 containing only benchmark data.

Across both resolver module layouts the 5 distinct file versions call the collision check immediately after cycle checking and build the full lockfile encoder state. They encode every resolved package and insert it in a map. The two observed function bodies differ only in the map constructor. Both proposed name/version shortcuts are absent.

- release 1.99.0-18 uses the full check. [Pinned source](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/resolver/mod.rs#L1065)
- Cargo default branch uses the full check. [Pinned source](https://github.com/astral-sh/ohm-cargo/blob/5819763564a25251b83e168217c619ee1f943293/src/cargo/core/resolver/mod.rs#L1067)
- Cargo 1.99 integration uses the full check. [Pinned source](https://github.com/astral-sh/ohm-cargo/blob/ec7a03b6b50c0ed2d9582c7e40d92a26a230c491/src/resolver/mod.rs#L1065)

The nearest posted changes affect collection choice, field formatting or decoding.

- [#11 Use FxHash collections throughout Cargo](https://github.com/astral-sh/ohm-cargo/pull/11)
- [#246 Format only the package identity fields a lockfile edge needs](https://github.com/astral-sh/ohm-cargo/pull/246)
- [#266 Resolve unique lockfile package names without nested maps](https://github.com/astral-sh/ohm-cargo/pull/266)
- [#271 Reuse decoded paths from interned local source IDs](https://github.com/astral-sh/ohm-cargo/pull/271)

PR #275 indexes workspace members by name when testing whether selected package specifications can use the existing resolve cache. Its other file tests that eligibility logic. The lockfile collision helper and caller have the exact release blob at the PR head. [PR #275](https://github.com/astral-sh/ohm-cargo/pull/275/files)

The API inventory, commit-to-blob mapping, complete Git-identified module texts and extracted caller/body evidence are saved alongside this report.
