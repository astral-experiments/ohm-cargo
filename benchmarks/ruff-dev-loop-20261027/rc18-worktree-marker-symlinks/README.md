# Generated worktree markers followed a final symlink in released Linux Cargo

An ordinary unchanged `cargo +ohm build --lib` on the published Linux `1.99.0-17` and `1.99.0-18` packages atomically replaced a dummy file outside a private target through an absolute symlink at `.ohm-worktree-seed-v7`. Cargo exited zero. The sole workload crate was fresh. Both Cargo invocations in the kernel trace were the rustup proxy and the actual Cargo process. The symlink survived. A writer needs the ability to replace that generated target entry before Cargo runs, and Cargo needs write permission on the victim’s parent directory. The fixture supplies both inside its own mode-0700 tmpfs directory. The host filesystem and the original installed SDK were mounted read-only during the tests.

## Five writers on the published -18 package

The eight-command fixture uses a normal local library, a local procedural-macro crate and a build script. The three policy markers are written before scheduling compilers, including on previously settled builds. The other two cases trigger their actual compiler/build-script writers. Each row used a separate victim.

| Actual write | Ordinary stimulus | Victim bytes on released Cargo |
| --- | --- | --- |
| Prepared namespace | Unchanged build, all artifacts fresh | `7` and LF |
| Denied namespace | Unchanged build, all artifacts fresh | `untrusted compile-time inputs` and LF |
| Local macro | Unchanged build, all artifacts fresh | `local procedural-macro outputs require trust at import time` and LF |
| Script result | Edit build script's declared trigger and run the real script | The 64 ASCII hex digits of the result digest and LF |
| Dep-info denial | A real script installs the private deny symlink after planning, then compiling a genuine `env!("LD_LIBRARY_PATH")` observation reaches the separate dep-info writer | `untracked Cargo output path in compiled code` and LF |

For the three fresh arms, the complete kernel exec inventory had only the Cargo proxy and Cargo. For each of the other two, it also captured the build script and one rustc compilation. In all five cases, selected `readlink` and `renameat` syscalls name the exact dummy path. The release left the marker symlinks in place, changed the victims' inodes and wrote the marker payloads. Explicitly disabling worktree seeds did not create a prepared marker on an empty target. On a previously prepared target the separate disabled-seeds test preserved the prepared marker’s victim bytes and inode. The denial policy can still write other markers in a previously prepared namespace.

The same eight commands with corrected Cargo `a19d515cc301c05ad345ad0d657508905c28a2c900e01963632724cfd3b7289a` and the official -18 rustc all succeeded. Each marker became a regular file containing the exact same bytes as the release wrote. All five victims retained their original bytes, mode and inode. An additional ordinary offline `cargo add --path ../localdep` on each Cargo preserved an intentional user-manifest symlink and updated the target Cargo.toml identically.

[Released policy writes](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/compiler/build_runner/compilation_files.rs#L847) · [Dep-info denial](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/compiler/fingerprint/dep_info.rs#L538) · [Script result](https://github.com/astral-sh/ohm-cargo/blob/7caf39914da1e28a67744ecbc963a5f26361474d/src/compiler/fingerprint/worktree.rs#L75)

## Release history and duplicate check

All 55 published Ohm tag-specific manifests through `1.99.0-18` were resolved to their own Cargo revision and inspected at both Cargo sources' historical layouts. The first 26 releases did not contain these generated-marker writers. The following earlier release dates describe inspected source. The published -17 and -18 binaries have the native reproductions above.

| First published release | UTC date | Cargo revision | Writers |
| --- | --- | --- | --- |
| `1.98.0-6` | 2026-09-02 | `bbf4a22e66d6d134b07b5c39bfde2c65c0f8e95f` | v5 seed and deny, dep-info denial and script result |
| `1.98.0-8` | 2026-09-03 | `1570321097f84278436d3c2bdf8962e8896d0970` | v6 plus local macro |
| `1.98.0-10` | 2026-09-07 | `65b7b12d192a975bf174368036300179cd26502a` | v7 marker names |
| `1.99.0-17` | 2026-10-28 | `a0c7d08c898d3fdff992f2f431dec57d2486add2` | All five writers. The ordinary freshly settled prepared-marker overwrite was reproduced on the published binary. |
| `1.99.0-18` | 2026-10-28 | `7caf39914da1e28a67744ecbc963a5f26361474d` | All five writers were reproduced on the published binary. |

Ohm's worktree-seed implementation introduced the prepared/deny/dep-info/script uses. The local-macro change added the remaining writer. Upstream Cargo had already deliberately changed the generic `write_atomic` helper in June 2025 to preserve symlinked user manifests. [Ohm #101](https://github.com/astral-sh/ohm-cargo/pull/101) · [Ohm #103](https://github.com/astral-sh/ohm-cargo/pull/103) · [Upstream Cargo #15281](https://github.com/rust-lang/cargo/pull/15281)

The pre-fix repository survey covered 282 live branches, 227 PRs in all states, and the 19 ordinary issues. The union of branch and PR tips had 286 distinct Git commits. Of those, 169 had the worktree marker writer under either Cargo source layout. Every such head retained the symlink-following writers, with two early heads preceding the local-macro marker. Issue #206 and PR #208 address relink cleanup through directory symlinks. PR #201 hardens reading nonregular cache files. PR #258 deals with checksums and ambiguous input paths. The scoped mechanisms differ from replacing a generated marker's symlink destination. [Issue #206](https://github.com/astral-sh/ohm-cargo/issues/206) · [PR #208](https://github.com/astral-sh/ohm-cargo/pull/208) · [PR #201](https://github.com/astral-sh/ohm-cargo/pull/201) · [PR #258](https://github.com/astral-sh/ohm-cargo/pull/258)

## Reproduction

`minimal.py` tests the prepared marker with four ordinary Cargo invocations, including a fully fresh repeat after installing the symlink. Each run creates a new owned tmpfs directory. `reproduce.py` contains the five-writer -18 fixture and all Cargo/Rust/build-script source. These Linux runners need an installed official SDK matching the recorded packaged image hashes, a rustup cargo proxy under `~/.cargo/bin`, Python 3.11+, bubblewrap, strace, and available CPU numbers. Pass the appropriate CPUs on a different machine. The corrected arm uses an additional read-only bind for only its candidate Cargo executable.

```sh
python3 -IB minimal.py --sdk /path/to/official17 --revision 17 --expect vulnerable --cpus 0,1
python3 -IB reproduce.py --sdk /path/to/official18 --expect vulnerable --cpus 0,1
python3 -IB reproduce.py --sdk /path/to/official18 --cargo /path/to/cargo-fixed \
  --cargo-sha a19d515cc301c05ad345ad0d657508905c28a2c900e01963632724cfd3b7289a \
  --expect protected --cpus 0,1
sha256sum --quiet -c SHA256SUMS
python3 -IB verify.py
```

The evidence contains selected raw syscalls and full trace commitments, workload exec inventories, tests and source-object receipts. It covers final absolute symlinks in namespace directories that are genuinely owned by the fixture. Parent-directory symlinks and simultaneous changes to directory ancestors are separate cases.

The first -17 namespace setup hid the separate SDK under its private /dev mount. Rustup rejected the very first command before starting Cargo. Its zero-observation receipt is retained. The four-command run mounted the same authenticated SDK read-only and started with a separate empty fixture.

The two source-survey files bind each observed branch name by SHA-256, each PR by number, and each unique head to its actual source blob IDs. Release tags retain their literal manifest paths and object IDs. Unrelated branch names and issue text are omitted from the packet.
