# Full Ruff CLI build storage after a branch return

The guarded compiler allocated 3,513,303,040 bytes across the whole Cargo target and shared build directory. Its parent allocated 2,418,098,176 bytes in the corresponding installation. The difference was 1,095,204,864 bytes, or 45.29%.

| Allocated bytes | Parent compiler | Guarded compiler |
| --- | ---: | ---: |
| All target and build-directory inodes | 2,418,098,176 | 3,513,303,040 |
| Inodes with an incremental path | 1,089,441,792 | 2,184,646,656 |
| Inodes with no incremental path | 1,328,656,384 | 1,328,656,384 |
| Incremental inodes also named outside an incremental directory | 42,074,112 | 42,074,112 |

There was one independently empty installation per compiler. Both built Ruff's historical feature branch, switched to its parent, returned to the feature, returned to the parent and ran one unchanged build. The measurement took place after this final Cargo process exited. The executable reported the precise parent commit. Its independent reader observed a 64-byte expression on the parent and a 56-byte expression on the feature. The ordinary CLI also passed its lint, diagnostic, actual fix, recheck, and malformed-input checks. Each branch return invoked 20 full rustcs and one stock Wild. The final unchanged builds invoked neither.

The two Cargo roots occupied the same private Linux tmpfs. The observer opened both as read-only directory descriptors, performed two complete metadata walks, and required the two ordered ledgers to match. It used lstat without following symlinks and counted 512 bytes per allocated block once per device and inode across both trees, including directory allocation. An inode with any path under an `incremental` component contributed to the incremental row. The fourth row is a subset of the second. Source, SDK, Cargo home, and the separately built reader were outside both measured roots. No compiler files were copied or removed for sizing.

The separate performance admission rejected both cross-compiler whole ELF comparisons. It produced zero elapsed samples. The loaded code and data of both full Ruff executables matched after masking the GNU build ID. The unstripped files also differed in debug info, macros and strings. Among 161,120 debug strings in the independently empty feature pair, the differing value was the Cargo-generated native build directory for `tikv-jemalloc-sys`. A subsequent independent clean build on the same baseline compiler also changed that directory. Cargo includes the installed compiler files’ identity in the directory name. Each compiler reproduced its own full feature-branch ELF on returning to that checkout. Its first parent checkout, return to parent, and unchanged parent also produced byte-identical files. The observations contain both compilers’ literal output hashes and the raw rejection commitment.

Run `python3 -IB verify.py` to check the data and the hardlink/active-session controls. To measure two settled, ordinary-user-owned Cargo directories on one filesystem, run `python3 -IB census.py TARGET_DIR SHARED_BUILD_DIR`. The standalone meter uses the same allocation and deduplication rules. Native command times were excluded from this storage acquisition.
