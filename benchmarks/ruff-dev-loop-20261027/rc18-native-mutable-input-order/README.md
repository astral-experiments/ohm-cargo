# A change between native input reads can produce a false link-cache hit

This is an unscored Linux x86-64 correctness experiment. A prototype BLAKE3 receiver accepted the old executable returning **41** while the only possible results of the actual linker were **97** and **83**. The Rust FFI program calls a C function and prints its return value. All eight ordinary builds used the same logical workspace, the matched pre-release R2 compiler and Cargo, and the stock packaged Wild binary. Each used a fresh target and build directory. The store includes the complete Rust sources, four old process traces, the synchronized native syscall receivers and four distinct full ELF bodies. Tool hashes and command lines are in the receipts.

The outer GNU linker script A selects either nested script B or an alternate returning 97. B selects either a C object returning 41 or one returning 83. Each script edit changes one byte. The independently built corners returned the following results.

| A | B | Native program |
| --- | --- | --- |
| 0 | 0 | 41 |
| 1 | 0 | 97 |
| 1 | 1 | 97 |
| 0 | 1 | 83 |

The checker reads the retained executable, both scripts, the alternate and all three C objects. Its own BLAKE3 implementation reads the pinned data descriptors through EOF, then checks the descriptors and resolves the names again. After it finished reading B0 and reached the first kernel pread of A, the controlled writer changed B to 1 and then A to 0. The actual states were A1B0, A1B1 and A0B1. Both pages had already been dirtied through ordinary writable shared mappings. All before, between and after inode fields checked by the native receiver were equal. The old bytes passed all seven checker rows. A fresh validation at the stable end rejected the proof.

The stock linker reads A to find the nested pathname. If it has consumed A1 before the writes it can only select 97. If it consumes A0, B1 was already visible. Two genuinely synchronized cargo builds executed the same writes at the outer and nested opens and produced 83 and 97. Each complete executable matched its independent empty-target corner. A separate direct-object case passed a single ordinary ELF object as an explicit build-script link argument. Changing only the x86 machine return immediate at the output-file open still gave 83, after the kernel had already mapped the object. Changing it at the object's open gave the same full ELF. The toolchain's ordinary system inputs remain present in that experiment.

Six attempts to take an advisory kernel read lease on the actual mapped script and object inputs failed with EAGAIN while their writable mappings were live and all local writable file descriptors were closed. All six succeeded after unmapping. A general admission rule also needs unchanged pathname resolution, including missing alternatives and the incumbent output. The separately collected native file and directory inventory determines whether a specific workspace can meet that precondition.

## Replay

Run `python3 verify.py` on Linux x86-64 to check the underlying physical syscall/process receipts, raw digests and outcomes, and to execute all eight recorded program cases from their full ELF bodies. The same four ELF body files serve several cases with identical SHA-256s.

Run `python3 replay-receiver.py --blake3-c /path/to/blake3-1.8.5/c --out /new/private/path` to build the candidate's exact hashing/descriptor-check code and reproduce the wrong acceptance on a new namespace of paths. It verifies all nine dependency source hashes first. This replay needs Linux x86-64, GCC, an ordinary writable filesystem and permission to observe its own child with ptrace. The crates.io blake3 1.8.5 source archive SHA-256 is `0aa83c34e62843d924f905e0f5c866eb1dd6545fc4d719e803d9ba6030371fce`.

The original four-Cargo generator and synchronized native supervisor are in `raw.tgz` as `original/opposite-order.py` and `synchronized/{actual.py,gate.c}`. Their physical run uses the paths and source-built compiler hashes recorded there. The initial diagnostic-only C compile warning and correction are retained. No measured timings are part of this packet. The exact private publication exporter recorded on H2 is preserved there. The portable export helper only encodes its public-filter match pattern to keep the pattern itself from triggering downstream publication scanners.
