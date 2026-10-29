# Recover a committed dependent after its producer fails

Official Linux Ohm 1.99.0-18 returns E0460 on the first source revert in the checked-in Cargo test `conditional_metadata_rebuilds_committed_dependent_after_failed_producer_is_reverted`. A second identical build succeeds. Cargo commit `34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31` repairs the first revert, including upgrades from an already failed -18 target. The resulting real program printed `1`, and the next build launched no rustc.

## The persisted failure

The test wrapper waits for the middle library to commit a genuine Cargo fingerprint after it used the upstream library’s changed metadata. It then injects the upstream failure. The middle library’s metadata and archive both differ from the initial generation. Its 16-hex Cargo short record is present. The upstream commit file is empty, its prior public-hash sidecar is absent, and its translated v4 dep-info still contains the BLAKE3 of the original source. Restoring those source bytes satisfies that old checksum. Released Cargo rebuilds the upstream library and final binary but accepts the middle library when it recursively plans that binary. The final real rustc reports E0460. The candidate makes a matching completed short record a prerequisite for treating an otherwise current metadata producer as fresh during that planning.

Under conventional mtimes the released and fixed executables both recovered immediately in this fixture. Explicit checksum freshness switches the otherwise identical timestamp case back to E0460 on -18. The immediately adjacent change that enabled worktree preparation by default first made this existing test fail by default. The original conditional-metadata implementation passes the test with the same rustc. Independent wrapper-free late assembler failure and SIGKILL controls on released -18 and the pending-metadata subjects recovered on their first reverted build. Those separate ordinary results do not establish E0460 for that construction.

## Native controls

`first-revert.json` records all six stationary mode and executable combinations, the source-content checksum, original Cargo dep-info bytes, the missing commit, typed real compiler jobs, diagnostics and program bytes. Digests bind raw process logs and complete target snapshots. A separate implementation from the locked BLAKE3 1.8.5 portable C sources verified the source checksums. The Git patch is relative to the pending-metadata fix `b3360c5eda186845b9a2ba6e5330a97c07d4acf2`.

The nine unmodified integration cases passed with the final Git-stamped dev Cargo and official -18 Rust. Fourteen checks in two scheduler orders returned the real E0034 error for the unchanged leaf on the edited, repeated and independently empty histories, and passed on restoration. All 407 Cargo library tests passed under the ordinary user and filesystem root. The initial user-namespace library run maps the root directory to uid 65534, which causes 17 existing private-directory trust tests to refuse their test setup. Its physical rerun used the same product source and a trusted filesystem root.

## Filesystem behavior

The first patch at `c3d09a7d05d3c6a6e9e060dacf488afe8c0acb1d` performed a speculative ordinary read. We created a writerless FIFO at a deep dependency’s short fingerprint and a directory in place of the terminal short. The parent Cargo returned EISDIR without reading the FIFO. The first patch blocked on the FIFO. The final patch uses an existing nonblocking, descriptor-checked regular-file open, accepts exactly 16 bytes, and verifies EOF. It returns the original EISDIR in both tested modes. An earlier 1 MiB file with the valid 16-byte prefix caused the first patch to read all 1,048,576 bytes. The parent and final candidate read zero bytes of its contents. All four units still reported fresh for a symlink to the original regular short. In the separate single-FIFO case all three executables reached the existing blocking owner read. Every deliberately blocked command had a four-second hard deadline and process-group cleanup.

## Hot-path cost

A successful locked comparison can be consumed once from the existing memoized hash. The first cached comparison still checks the current filesystem status. Later comparisons reopen the short, and clearing the memoized hash also deletes the match. On this x86-64 Linux build the old and new value occupy 16 bytes and their mutexes each occupy 24 bytes. In the four-unit fixture normal Ohm performed two successful short reads per unit in both the parent and final candidate. With Ohm defaults off each performed one. On a fine-grained, nonexclusive checksum build the parent performed one and the candidate two. In a separate real shared-registry graph, the parent performed two reads on both the locked workspace consumer and the shared `itoa` crate; the candidate performed two and three respectively. These raw syscall results count opens of the short commit file. They do not estimate wall time.

Recheck the six histories and mutate seven independent evidence fields with

```sh
python3 -IB verify.py --selftest
```

The existing regression can be run from the corresponding Ohm Cargo checkout with its normal testsuite environment and stable, separate build directories.

```sh
cargo +ohm test --locked -p cargo --features ohm-defaults --test testsuite -- freshness::conditional_metadata_rebuilds_committed_dependent_after_failed_producer_is_reverted --exact
```
