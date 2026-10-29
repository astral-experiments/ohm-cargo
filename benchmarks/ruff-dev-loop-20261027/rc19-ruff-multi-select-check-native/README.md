# A historical Ruff manifest edit triggered 51 compiles during cargo check

Ruff commit `2d6ce561250a464e1fa231ef30e54d0f029f76a4` changed library test or doctest selection in 27 packages. Its 30 changed files consist of 29 Cargo manifests and a CI workflow. No Rust source, dependency declaration or lockfile changed. Cargo selected all 47 members by default. The public source inventory records both complete revisions and their exact semantic differences. [Ruff commit](https://github.com/astral-sh/ruff/commit/2d6ce561250a464e1fa231ef30e54d0f029f76a4) · [Source inventory](https://github.com/astral-sh/ohm-cargo/tree/d0325acfadb4c8e38ee5a669f665d58c20f13c88/benchmarks/ruff-dev-loop-20261027/rc19-ruff-multi-select-subject)

On one Linux machine, we ran `cargo +ohm check --workspace --locked --offline -j8 --message-format=json` with two Cargo binaries. One is from the published Ohm 1.99.0-18 distribution. The other is the matching release-PGO build of `235f9228651b74c591e6f62cae4c9b761448dd2d`, pinned by the proposed -19. Each had its own Cargo-created Ruff worktree and target and build directories. They used the exact shipped rustc and Wild. The proposed Rust pin differs from -18 only in the Cargo submodule. Each direct edit rewrote only the 30 differing files using their exact Git object bytes. Source checks used filesystem reads. The Git administrative directory and all its sampled entries remained unchanged through each command. An earlier diagnostic that also called Git status produced different process counts and is excluded here. [Cargo pin](https://github.com/astral-sh/ohm-rust/pull/249)

| Native commands | Published -18 | Qualified Cargo |
| --- | ---: | ---: |
| Settled check before the change | 1 rustc | 1 rustc |
| Restore the parent manifests | 51 rustc, 1 Wild | 51 rustc, 1 Wild |
| First unchanged parent check | 24 rustc | 12 rustc |
| Second unchanged parent check | 1 rustc | 1 rustc |
| Reapply the committed manifests | 51 rustc, 1 Wild | 51 rustc, 1 Wild |
| First unchanged committed check | 12 rustc | 12 rustc |
| Second unchanged committed check | 1 rustc | 1 rustc |

Each edited check reported 510 typed artifacts, including 56 dirty artifacts. Cargo logged 30 target-configuration notices, 26 dependency-information notices and one precalculated-components notice. Those notices are a separate count from compiler work. A Linux exec observer matched actual Cargo, rustc, GCC, collect2 and the stock Wild by device and inode after verifying their binary hashes. The linker produced the `ruff_macros` procedural macro shared library. Within each Cargo version, all 51 complete rustc command lines had the same literal byte hashes in both source directions.

This packet measures work counts. It contains no candidate implementation or performance timing. Actual proc macros can read a caller's manifest, and compiler arguments alone do not establish safe reuse. `observations.json.gz` contains each typed unit, each native event and its complete original argv hash, all fingerprint reason categories and the SHA-256 digests of the original private logs. Run `sha256sum -c SHA256SUMS && python3 -IB verify.py --mutations`.
