# Release Cargo on existing -19 targets

Cargo `8dc33c9c`, SHA-256 `8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5`, repaired each tested target under the defaults. The same release-profile binary was paired separately with the published -19 compiler (`eef2f342`) and a source-attested local compiler (`ca780121`). Both used the unchanged packaged Wild. Each history started on the verified published -19 Linux distribution. Before switching the private SDK alias, we recorded the current source and target files by path, inode, size, mtime and complete content digest. The alias changed while those files stayed in place.

| Existing target | First command after upgrade | Independent control |
| --- | --- | --- |
| Ambiguous method call previously accepted by -19 | E0034 twice at `client/src/main.rs`, line 3, columns 30–38 | Same primary span on empty targets before and after upgrade |
| Dependency reverted after a failed compile | First build succeeded and the regular executable printed `1` | The original program printed `1` before the injected compiler failure |
| Changed native archive | The integration test linked and printed `29` | A subsequent unchanged command ran zero compilers and linkers |
| Malformed earlier native archive | Cargo returned 101 with a Wild diagnostic naming `early/libchoice.a` | Reversing the edit produced `29`. Restoring the fallback produced `17` |
| Assembler input edited from byte 17 to 29 | First unchanged build repaired `9:17` to `9:29`, then the repeat ran zero compilers and linkers | Both an independently empty target and an actual traced read of byte 29 agreed |
| Assembler input removed | Cargo returned 101. The compiler attempted to open the missing file | Empty build also returned 101. Restoration printed `5:17`, followed by zero compilers and linkers |

**Explicit `-Zrelink-only=yes` remains unsafe on this case.** With the same Cargo and `ca780121` compiler, the changed build ran cached-codegen rustc and stock Wild, never opened the current assembler operand, and printed `9:17`. An independent empty build with the same flags read byte 29 and printed `9:29`. All assembler cases used `CARGO_INCREMENTAL=0`.

The E0034 fixture orders publication of the two already compiled parent fingerprints. The first-revert fixture uses the established compiler wrapper to force the failing schedule. The native provider and assembler fixtures use ordinary Cargo invocations and real compiler/linker processes. Trace and program-output digests are included alongside the observed values. No elapsed-time result is reported.

Use `sha256sum -c SHA256SUMS` and `python3 -IB verify.py` for offline verification. On Linux with the two private SDKs, rustup, strace and cores 24–27, run `taskset -c 24-27 python3 -IB reproduce/replay.py RELEASED_19_SDK CANDIDATE_SDK NEW_DIRECTORY`. Repeat with the other candidate compiler in a separate directory. To reproduce the explicit opt-in control, run `taskset -c 24-27 python3 -IB reproduce/optin.py CANDIDATE_SDK NEW_DIRECTORY`.
