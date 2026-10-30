# How much of Ruff's second checkout could be duplicate object files?

The extra 908 incremental object files occupy **174.20 MiB** in the final full-CLI checkout. Across both complete Cargo directories, whole-file deduplication could recover **at most 76.43 MiB** of that allocation. The published collection did not record full object contents or per-object digests. It therefore establishes **no positive number of reclaimable bytes**. [Original disk study and native controls](https://github.com/astral-experiments/ohm-cargo/tree/01229f4bd256496a863d56a6e8822febf55ad2c8/benchmarks/ruff-dev-loop-20261030/branch-switch-incremental/storage/alternatives/switch-only/full-ruff-cli)

The original experiment built `ruff` with Rust `08d49cba6aac`, first on A, then on B, then on each branch again. The final unchanged B recompiled nothing. This analysis reads six published inode ledgers. A and B below are the alternate and current checkout in the same installation with retention on. The separate installation with retention off supplies the total object-allocation comparison. The units are MiB (1,048,576 bytes).

| Same crate and codegen-unit filename in A and B | Count | A allocation (MiB) | `ruff_linter` count | `ruff_linter` A allocation (MiB) |
|---|---:|---:|---:|---:|
| Already the same inode | 889 | 32.80 | 4 | 0.46 |
| Distinct inodes, different byte lengths | 307 | 98.00 | 206 | 81.14 |
| Distinct inodes, equal byte lengths | 601 | 76.20 | 46 | 8.95 |

The first row was already charged once. In these 20 units every codegen-unit object has a counterpart by filename in the other checkout. Allowing different filenames in the same unit adds zero possible matches. Of `ruff_linter`'s extra 90.09 MiB, the 206 objects in the second row each have a unique file length among **all 3,589 native object inodes** in the combined roots. The 46 in the last row need a full byte comparison.

### Deriving the physical ceiling

1. Identify the 20 incremental crate directories containing both checkout keys. Match the ordinary `.o` files by crate directory and basename. Count allocated blocks once per `(st_dev, st_ino)` across Cargo target and build. All 908 A-only inodes have their entire link count represented by names in A's session directories.
2. Group every standalone native object in both roots by its *logical byte length*, allowing unrelated crates and filenames. All 3,589 were ELF relocatables. If a length has at least one object outside the 908, provisionally allow removal of every alternate-only object at that length. If all objects at that length are alternate-only, at least one must remain. Keep the one with the smallest allocated size for a conservative upper bound.
3. This excludes 292 unique-length alternate objects (102,473,728 bytes) and one additional representative (45,056 bytes). At most 615 alternate inodes, or **80,142,336 allocated bytes**, could disappear. At least **102,518,784 bytes** would remain under even this permissive whole-object policy. File lengths give no basis for assuming the 615 contain matching bytes.
4. Within the 20 affected units, all 1,797 objects on each branch preserved their device, inode, size, allocated blocks and mtime from the original branch visit through that branch's return. This includes every one of the 908 branch-specific objects on each side. The observation records inode continuity. The ledger does not record per-object compiler opens, an instruction count or payload checksums. The original complete CLI/runtime and independent clean controls remain in the linked study.

The ceiling applies to exact whole-file identity among standalone native object inodes on the observed Linux tmpfs. It does not bound compression, shared extents inside unequal files, archive-member-backed storage or any other workload. Directories, lookup indices, comparison I/O and implementation overhead are outside the ceiling.

### What rustc already does

Rustc holds the selected finalized session's shared lock while it creates a private working directory. On Linux it hard-links ordinary objects and falls back to copying if hard-linking fails. When reusing a codegen unit, it records the known link and avoids linking the same work product back a second time. A CGU filename identifies an indexed work product. Reuse additionally requires the saved files and a green codegen dependency node. If an indexed object is removed, rustc discards the incomplete work product and can run codegen again. [Session setup](https://github.com/astral-experiments/ohm-rust/blob/08d49cba6aacb0cac27a96eea335ed1c7439f483/compiler/rustc_incremental/src/persist/fs.rs#L397-L469) · [Work-product loading](https://github.com/astral-experiments/ohm-rust/blob/08d49cba6aacb0cac27a96eea335ed1c7439f483/compiler/rustc_incremental/src/persist/load.rs#L65-L89) · [Saving known links](https://github.com/astral-experiments/ohm-rust/blob/08d49cba6aacb0cac27a96eea335ed1c7439f483/compiler/rustc_incremental/src/persist/work_product.rs#L22-L57) · [Codegen reuse](https://github.com/astral-experiments/ohm-rust/blob/08d49cba6aacb0cac27a96eea335ed1c7439f483/compiler/rustc_codegen_ssa/src/base.rs#L1288-L1333)

Ohm already clones sessions on supported macOS filesystems, collects superseded sessions, and reuses stable paths for unpacked debug objects. Its ThinLTO caches serve a different backend configuration. None of those changes compares fresh native object payloads across the two retained default build sessions. The saved-link isolation fix deliberately gives externally writable `.rlink` objects independent inodes. Reconnecting those paths to an incremental cache by hard link can turn an external write into a stale successful build. [Session clones](https://github.com/astral-experiments/ohm-rust/pull/79) · [Session GC](https://github.com/astral-experiments/ohm-rust/pull/97) · [Unpacked debug objects](https://github.com/astral-experiments/ohm-rust/pull/98) · [Incremental ThinLTO](https://github.com/astral-experiments/ohm-rust/pull/155) · [Non-incremental ThinLTO](https://github.com/astral-experiments/ohm-rust/pull/164) · [Saved-link isolation and reproducer](https://github.com/astral-experiments/ohm-rust/pull/268)

### Which lower-storage test would answer the question?

1. In a **future** native installation, after the ordinary command exits and before scratch release, hash the equal-length candidates once per inode, then byte-compare matching pairs. Charge 512-byte `st_blocks` once per removable inode, preserve independent exported links, and record real Cargo work and clean CLI behavior on both returns. This gives a real denominator before any deduplication implementation.
2. For `ruff_linter` in particular, byte-preserving compression is testable even for the 81.14 MiB ruled out for whole-file matching. Measure actual packed blocks and exact restoration of actual branch-specific objects without changing compiler decisions. A subsequent native experiment would have to count return compilers, codegen work, clean ELF/verdict parity, corruption fallback, simultaneous readers and the cost of packing and restoration. These ledgers supply no compression ratio or return cost.
3. For a zero **extra retained-state** policy, today's default `-Zohm-branch-cache=no` already keeps the latest successful session. A possible selection-only mode could take a shared lock on a matching finalized session *only if another legitimate owner already kept it alive*, and retain nothing beyond normal GC. If none exists it uses ordinary incrementality and keeps the latest successful cache intact. This would give no guaranteed alternate hit on the measured serial A/B history. A strict budgeted retention policy should likewise decline the alternate whenever its blocks and directory overhead cannot fit after protecting the active session. Neither policy has a measured speed or peak-storage result here.

### Reproduce

From this packet directory, with a checkout of the evidence repository already at the commit below:

```sh
repo=/path/to/ohm-cargo-evidence-checkout
test "$(git -C "$repo" rev-parse HEAD)" = 01229f4bd256496a863d56a6e8822febf55ad2c8
census="$repo/benchmarks/ruff-dev-loop-20261030/branch-switch-incremental/storage/alternatives/switch-only/full-ruff-cli/census"
sha256sum --check SHA256SUMS
python3 -IB verify.py "$census" --check
```

The script uses Python's standard library and does not run Cargo, access a devbox, or read any native payload. `inputs.json` pins each compressed input. `results.json` includes the individual 20 units and both return checks.
