# A script-free native archive can falsify the retained link result

A Rust FFI program calls one input object. Its sole unresolved native symbol selects one of two members of a conventional static archive. The two user-supplied linker inputs are a relocatable ELF object and a GNU archive. Their names and order are unchanged, as are the archive's member names, order and symbol index. One byte in the object's undefined ELF symbol name selects branch0 or branch1. One byte of x86 machine code in the archive member for branch0 changes its return value from 41 to 83. The other member always returns 97.

Four independent empty-target builds using ordinary `cargo +ohm build --locked --offline -j1` produced the following executables. Every readelf, nm, ar and runtime observation can be replayed against the included raw files.

| Dispatch | Archive branch0 | Only native branch in final ELF | Runtime |
| --- | --- | --- | --- |
| branch0 | 41 | branch0 | 41 |
| branch1 | 41 | branch1 | 97 |
| branch1 | 83 | branch1 | 97 |
| branch0 | 83 | branch0 | 83 |

The native validator hashes the archive followed by the dispatch object. Stop it at its actual first pread of the dispatch object after it reached EOF on the archive. The live writer changes the archive return from 41 to 83, then the dispatch name from branch1 to branch0. The extant 41 ELF and the two whole mutable files passed the original BLAKE3 validator while the three reachable steady states returned 97, 97 and 83. Their checkable descriptors and path stat fields were unchanged. The next stable attempt rejected the old ELF.

Three additional ordinary builds place writes relative to genuine stock linker operations. Stopping at the dispatch open allowed branch0 and produced 83. Stopping after resolution when Wild opens the final output selected branch1 and produced 97. Holding the dispatch unchanged at branch0 and changing the archive byte at the same output open produced 83. Both inputs had already been mmap'd by that point. The last control identifies when Wild still observes the selected member's actual bytes. Each synchronized complete ELF matched its corresponding independent clean build.

The linker cannot produce the retained 41 through this ordered edit. Choosing branch1 yields 97. To choose branch0 the dispatch symbol must be read after it changes, by which time the member already returns 83, and the code bytes are obtained after selection. An earlier map of the archive does not provide a frozen copy. The source-bound stock check used genuine matched pre-release R2 rustc and Cargo plus the original distributed Linux Wild. Standard toolchain inputs were held fixed in all seven builds. There are no project linker scripts, higher-priority search paths or different native flags in this example.

Run `python3 verify.py` to check all raw data digests, extract both archive members, inspect the actual relocation/symbol tables and execute all seven recorded programs. Run `python3 replay.py --reference /path/to/rc18-native-mutable-input-order --blake3-c /path/to/blake3-1.8.5/c --out /new/private/path` on x86-64 Linux to repeat the actual three-row receiver failure with its pinned implementation, a fresh build and its own child ptrace permission. The complete Cargo and syscall-gate sources and traces are inside raw.tgz. An earlier diagnostic supervisor lost a short-lived process before it inspected the stopped syscall and exited 95. Its original output is retained. All seven reported results came from the subsequent supervisor that tolerates that exit and still requires a genuine stock binary-specific barrier.
