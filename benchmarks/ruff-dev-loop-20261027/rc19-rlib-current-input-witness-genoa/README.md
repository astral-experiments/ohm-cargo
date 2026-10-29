# Genoa current-input witness for the Ruff linter archive

Both compiler invocations passed the independently published correctness protocol. The ordinary writer and the experimental checked writer each produced a 101,719,820-byte native rlib identical to an independent GNU archive rebuild of its own 258 real input descriptors. The two invocations had different object names. Each went through the unchanged ordinary cargo/rustup route on the historical SIM222 edit, using separate writable Btrfs volumes and the same compiler, standard library and Wild. [Registered source and protocol](https://github.com/astral-sh/ohm-cargo/tree/a644772c28607282fc06bb7c72f08225ea04f0a6/benchmarks/ruff-dev-loop-20261027/rc19-rlib-current-input-witness-plan)

| Cargo arm | Full rustcs | Support probes | Native links | Real target clones | Independent whole archive SHA-256 |
|---|---:|---:|---:|---:|---|
| Ordinary | 10 | 0 | 0 | 0 | `f6270ca22407df33475511cdc7bb6bf476e0250399199a8b7193a44af35abc94` |
| Checked | 10 | 1 | 0 | 1 | `11f62fc8d0af7dcc613172d3b8b2981ada850c77e6416d8bdcd7120b4488849e` |

The observer captured both wrapped metadata files and 256 real codegen objects before each selected rustc published its archive. The experimental rustc successfully issued FICLONE to its own temporary archive using the original inode held across the command. Both original descriptors retained their original bytes and mtime after publication. Each immediately repeated build reported all 248 units fresh and launched only Cargo. Ubuntu `llvm-ar` 18.1.3 received the captured, ordered inputs and an empty output directory. Renaming just one object and altering one current metadata byte produced separate wrong digests in both arms.

The four external callers compiled against the real and reconstructed archives produced the same full ELF (`c43c4296…`) and reported SIM222 on lines 2, 3 and 4. A separate 248-unit empty build of the edited source reported the same lines and produced a different complete caller ELF (`1fc06e57…`). The authenticated clean historical reference reported line 1 and had a third ELF (`06bd72dd…`). Both empty runs had zero initial fresh artifacts and all 248 fresh on the immediately repeated build. The complete ELF and archive hash values are retained separately from behavioral checks.

All 256 selected native objects per invocation were opened directly in the selected unit’s output directory. Their seven-character tokens were `1xd8syk` and `1lt32ns`. The FD observer recorded opens and publication. The older inotify window observer discarded other basenames, so these records do not establish a per-name inotify creation receipt.

Initial staging tried to send a Btrfs subvolume from a read-only loop device. The kernel rejected it before sending data. The runner then read the complete prior disk with `O_NOATIME`, verified its exact 10 GiB contents against a disposable block copy, and sent the immutable snapshot from that copy to both new filesystems. All 452 declared starting files matched bytes, mode and mtime. The operating-system failure and its digest are preserved. The measurements are unscored Linux x86-64 native correctness controls with a stage1 compiler.

Run `sha256sum --quiet -c SHA256SUMS` and `python3 -IB verify.py`. The packet retains SHA-256 bindings for raw executions, both typed rosters, the full ordered member and input inventories, held output inode states, external reader verdicts and independent archive outputs. The complete input captures, per-exec argument bytes and original writable histories remain on the native host.
