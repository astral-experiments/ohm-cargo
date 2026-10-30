# Concurrent incremental session retention

On Linux, two actual rustcs compiling distinct, clean Git checkouts shared the same crate name, disambiguator and incremental directory. They emitted separate native executables. An ordinary Cargo invocation with each source-built SDK supplied the guarded native option and stock linker flags for the direct calls. Every successful binary matched its independently empty counterpart across both compiler arms, including the entire 433,992-byte ELF and its execution. A/B/C produced 17, 29 and 41.

Two live macro barriers placed both processes in distinct working sessions at once. The compiler's actual nonblocking exclusive `flock` and each lock's device/inode were verified through Linux fdinfo and the raw traced calls. For the deliberately aged peer (11.079 s on the parent and 11.068 s on the guarded compiler), the other compiler's real garbage collector received EAGAIN. A failed participant exited with E0308 at the same source span as a genuinely empty failure, both when it finished first and after its sibling had published. The successful sibling's full native output and verdict were independently verified in each case.

| Finalized directories | Parent #269 | Guarded 6b7f424e |
| --- | ---: | ---: |
| After serial A/B/C revisits settle | 1 | 2 different checkouts |
| With an old finalized session held under a real shared read flock | 2 | 3 |
| After releasing that lock and settling again | 1 | 2 different checkouts |

`result.json` projects 42 direct rustcs, 36 stock native links, six expected failures and eight overlap/retention cases. The 690 original, per-thread kernel traces supplied 1,310,503 bytes. Native raw custody remains separate. The held FD reports the owning process ID, while the syscall trace identifies the worker thread. Timing is recorded only to prove the compiler's ten-second abandoned-session threshold was crossed. These tests make no performance claim. This fixture exercises Linux flock on a single ext4 host and does not generalize to other kernels or filesystems.

Verify the archived results with `python3 -IB verify.py`. For an independent native reproduction, run `python3 -IB run.py --help` and supply the complete two exact SDKs, guarded product directory containing product.json and completion.json, rustup proxy, a new private output directory and the volume to reserve as HOME. The replay preserves the original four cores and memory/storage admissions. Its configuration takes paths as arguments and omits the discarded earlier donor's local filename. The compiler commands, checks, native-fixture sources and overlap ordering come from the sealed acquisition. The initial exploratory SDK candidate had Cargo 7277 and failed identity admission before either tool ran.
