# Recovering an integration-test executable after a same-version Cargo replacement

A Cargo with the original integration-test shortcut can leave a stale executable in an otherwise settled target. Replacing Cargo with a version that invokes the real linker on dirty builds did not repair the next unchanged command when both Cargo binaries advertised the same complete version. Adding a generation to the affected integration-test fingerprint repaired the first unchanged command. The following unchanged command reused the repaired executable. [Cargo #281](https://github.com/astral-sh/ohm-cargo/pull/281)

## Same-version replacement

A pure Rust library and its integration test ran inside a private Linux filesystem namespace. An ordinary library-body edit coincided with a change to GCC's implicit `libgcc_s.so` linker script. The valid script brings in an object that exits 83 before the Rust harness starts. The malformed script makes a real link fail. Neither fixture uses a build script, an explicit native library or custom Cargo flags. Each history trained and confirmed the stale executable at 17 before replacing or retaining the SDK. All held source and build files were compared by path, contents, device, inode, size and modification time across the swap, including 104 files in each of the eight implicit histories.

| Cargo used for the next unchanged command | Valid script, first and repeat | Malformed script, first and repeat |
| --- | --- | --- |
| Original executable retained, four controls | Both tests still printed 17 | Both builds succeeded and the test printed 17 |
| Real-link fix without a new fingerprint | Both tests still printed 17 | Both builds succeeded and the test printed 17 |
| Real-link fix with a new fingerprint | Both executables exited 83 | Both Cargo commands failed with a native linker diagnostic and exit 101 |

For the unsalted real-link fix, a genuine subsequent edit did invoke the linker and produced the correct opposite verdict. Both repaired arms returned to 17 after restoring the original script and Rust source. All three development Cargo ELFs report identical `cargo -Vv`, including revision `34dad66fd`. Their full binary digests, separate source commits and the single production patch are recorded in `development-subjects.json` and `migration.patch`. They shared the same compiler and linker in the held study. The source carrying the fingerprint change is `2447f7f4eacb4fdf499899929f08d0de19abb4d0`, on `fd872c053bb1e9dcde722cf90a05a7cb8335dd32`.

## Released Linux package and independent outputs

An ordinary provider build script supplies two native search directories through a middle package. Separate provider-build and integration-test invocations resolved the same physical Cargo OUT_DIR. With the released 1.99.0-19 SDK, both the valid provider change and malformed input left the old executable printing 17. Keeping that release installed reproduced both stale outcomes. Replacing it with either development real-link SDK repaired the first unchanged command. The valid program printed 29 and the malformed input failed during linking. These two cross-SDK upgrades changed both compiler and Cargo identities. The same-version comparison above isolates the contribution of the new fingerprint.

Two independent empty-target builds produced executables that were physically reopened and hashed in full. Their SHA-256s matched the whole file recorded after the first repaired upgrade.

| Valid native change | Actual empty-target verdict | Whole ELF SHA-256 |
| --- | --- | --- |
| Implicit GCC script | Native exit 83 | `543fcfd64d6c6e055518a32c54d503981980b3390a0d524dcd4105e6ddb943f0` |
| Transitive provider | Test printed 29 and passed | `2d82c3c78e55c0f794b1157d3a3236976872fba5f623d7144770593d0c8313d3` |

The independent malformed builds each had two genuine compiler and linker attempts at the test before Cargo returned 101. The comparison for those commands covers their failure diagnostics. The official release archive was 359,628,600 bytes, SHA-256 `ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812`. `official-19.json` records complete Cargo and rustc versions and the installed binary digests.

## Target selection

A separate two-package workspace trained eight typed targets with the unsafe and fixed Cargo binaries sharing the same reported version, using the official -18 compiler. The first upgraded native test build recompiled one integration test belonging to the package with a library and invoked stock Wild once. The other seven targets were fresh, including the binary-only package's integration test. All eight were fresh on the second run, on both upgraded `check --all-targets` commands and on both upgraded defaults-off test builds. The executable hashes in the healthy settled states remained identical. This control measures work counts, with no wall-time result.

## Verify or repeat

Run the following from this directory. The offline reader needs Python 3.11 or later. It reopens the projected Cargo JSON, compiler and linker execve records, native stdout and stderr, individual file commitments, typed scope rows and held-state evidence. The synthetic mutations change a whole-ELF digest, exit, source hash, freshness flag and executed compiler. The manifest covers the verifier and replay inputs.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --selftest
```

To run fresh native histories, use private absolute directories that do not exist yet. The first example needs a Linux x86_64 GNU GCC 13 sender, `strace`, `as`, a rustup Cargo proxy and permission for a private mount namespace. It binds a task-owned copy of a single system script before dropping privileges, and verifies the host file's original inode and bytes afterward. The declared-provider and target-scope examples run as an ordinary user. Repeat each native case with the other poison value for the complementary history.

```sh
python3 -IB run-implicit.py /absolute/old-sdk /absolute/fixed-sdk /absolute/new-implicit malformed
python3 -IB replay-declared.py /absolute/official-19-sdk /absolute/new-declared --replacement /absolute/fixed-sdk --poison valid --stage-producer provider
python3 -IB replay-scope.py /absolute/new-scope /absolute/old-cargo /absolute/fixed-cargo /absolute/official-18-sdk
```

`acquisition.json.gz` binds original and projected byte lengths and SHA-256s for the 1,504 files in `streams.tar.gz`. Absolute study paths are replaced by stable aliases in its portable records. The ledger also records original acquisition-source hashes, tool bytes, full compiler versions, target snapshots and the two reopened ELF headers and digests. `replay-smoke.json` records two genuinely executed eight-command histories using the packaged runners, separate from the original corpus.
