# Native branch-retention compression on repeated, same-branch Ruff edits

Two mirrored installations compared source-bound Rust c9119d267c98 (raw retained sessions) with 8ea2252344ba (in-process zlib). Both used the real Cargo #294, the same 53 standard-library files and stock Wild. Both enabled the experimental checkout cache and Cargo's native-input protection. Each arm bound its matching native launcher and driver to their original immutable inodes across every installation. Both verbose Rust versions display the held 9f8db07 stamp. The build products, ELF launcher dependencies and driver hashes identify the actual code.

The workload alternated A and B of Ruff #28335, then reverted and restored Ruff #28233's unary-pattern rule twice as an uncommitted edit on the same B branch. Independent empty B and C builds on each compiler plus independently empty A roots fix the actual reference outputs. All 68 commands emitted 97 legitimate Cargo artifacts. Each warm grammar edit dispatched just the parser, each branch return dispatched AST and parser, and each immediate unchanged B dispatched neither. Off-clock registrations found zero native linkers during these library build steps. A separate real native rustc reader linked those libraries and returned the exact ELF and verdict for every recorded state.

Mean seconds across the two mirrored blocks follow. The right column retains the compact-minus-raw difference in each block, in seconds. First visit, returns, repeated edits and unchanged calls have their own rows.

| Real Cargo operation | Raw | Compact | Block differences |
|---|---:|---:|---:|
| First visit to B | 9.253 | 9.251 | -0.019, +0.013 |
| Immediate return to A | 2.806 | 2.967 | +0.065, +0.258 |
| First visit + return | 12.059 | 12.218 | +0.046, +0.271 |
| Trained return to B | 2.861 | 3.607 | +0.833, +0.659 |
| Two B→C grammar edits (sum) | 5.383 | 6.246 | +0.973, +0.752 |
| Two C→B restorations (sum) | 5.338 | 6.009 | +0.575, +0.767 |
| All four dirty same-branch calls (sum) | 10.721 | 12.255 | +1.549, +1.519 |
| Next unchanged B | 0.184 | 0.204 | -0.010, +0.050 |
| Return A after edits | 2.686 | 3.492 | +0.616, +0.994 |
| Return B after edits | 2.710 | 3.584 | +0.900, +0.849 |

The average additional same-branch cost per genuine edit/restoration was +0.383 seconds (+0.387, +0.380 by block). At the first settled B after the edits, whole target plus shared build occupied 378.09 MiB raw and 279.04 MiB compact, including 107.20 and 61.29 MiB present only in alternate sessions. Storage counts global allocated blocks once per inode across the two trees, verified against du. Each unchanged command reused that state.

In an earlier separate run of the **same 8ea compiler**, default retention-off versus retention-on saved 5.741 s returning to A and 5.337 s returning to B. Dividing those prior savings by the new estimated per-edit overhead gives approximately 15.0, 13.9 dirty grammar calls per saved return. This combines two distinct small experiments for scale. Each timing block shares a host with independent work on disjoint cores. The repeated edits within one installation share a target and are not independent trials.

The source sets `compact_branch_cache` upon seeing another branch's finished session, including on a dirty same-branch compile. Within each off-clock compact dirty edit the genuine compiler thread read both packed tables and created replacements for both. The raw role generated no packed-table calls. Both the native process rosters and the packed-file thread/PID/inode joins were checked from original kernel and live procfs observations. The sample concerns this native Rust implementation. The external flate2 wrapper is a separate earlier experiment.

The two complete native archives from each independent B/C reference, including their standalone .rmeta files, were physically reopened. Whole archive byte matches on traced and untraced dirty warm arms were 0/104. The unordered native .o payload multiset matched the independent same-role, same-source reference in 104/104. The metadata-member pair differed from the empty reference in all 104 dirty comparisons. The projection records whole archive hashes, actual native object payload multisets, and both metadata members separately for every phase. The runnable reader ELF matched in every case, including B rejecting and C accepting the specific signed pattern. The raw R and compact K reference SHA-256s were

  K/A  36af3a792d0f880908d64b9532d9d748f1fd6bba55c087b09fc116144fc5e945
  K/B  fb4b9d92a8299af6aa7e289d70a18e7b5328c24f62e992d4ab89f987be36a710
  K/C  6640ba266ff0e427e618a0b20bac514015126d62d32764c0664b13b91069bc80
  R/A  36af3a792d0f880908d64b9532d9d748f1fd6bba55c087b09fc116144fc5e945
  R/B  fb4b9d92a8299af6aa7e289d70a18e7b5328c24f62e992d4ab89f987be36a710
  R/C  6640ba266ff0e427e618a0b20bac514015126d62d32764c0664b13b91069bc80

Run `sha256sum -c SHA256SUMS && python3 -IB verify.py`. The offline verifier recomputes every pair-level cost and the storage analysis from the projection. On the host retaining the original study directory, `python3 -IB verify-originals.py <study-root>` independently reopens native files and compressed per-thread work and reproduces observations.json SHA-256 41c45f9467801c1313fd226942f5cc806214608901c23254f9bfac2a30b968aa. Retained originals include the 8 private ext4 targets, typed Cargo streams, compiler products, digest-bound complete ELFs, and compressed per-thread native syscalls for all 16 off-clock controls.
