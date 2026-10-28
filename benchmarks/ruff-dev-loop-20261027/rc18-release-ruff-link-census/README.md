# Ohm 1.99.0-18 on the Ruff native test graph

On Linux x86_64, two unchanged whole-workspace Ruff test builds each recompiled `ron`, ran 50 link-only rustc processes and executed 50 stock Wild linkers. The focused `ty_server` e2e command reported all 300 units fresh on both repeats and executed zero compilers or linkers. A real source change altered the e2e executable and two notebook test outcomes. Restoring the source recovered the original executable in both scopes.

## Release and setup

Ruff was at `93526150df078af7dd8fc4226cdcc469539d2001`. The experiment reversed the notebook range fix from `eb9e9bdcf988fffcd619dcf5d2a2bd74d75be1c6` in `crates/ty_server/src/document/range.rs`. The source digests, lockfile-based registry inventory and exact Cargo arguments are in the records. The whole command was `cargo +ohm test --workspace --no-run --locked --offline -j8 --message-format=json`. The focused command selected `-p ty_server --test e2e`. [Ruff source edit](https://github.com/astral-sh/ruff/commit/eb9e9bdcf988fffcd619dcf5d2a2bd74d75be1c6)

The public Linux archive was 359,656,945 bytes, SHA-256 `629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8`. The first installation used the archive’s own installer on the original CI-built bytes. After publication, the public outer installer installed the separately downloaded archive with the same digest. The public installer SHA-256 was `0148622878ce6a6278c31b7652563090e522aadb8be9f7282da28018061a2d07`. The recorded release manifest and provenance digests are in `release.json`. [Official release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-18)

The comparison covered every one of the 69,866 files and symlinks in each installation. The compiler, Cargo, stock Wild and runtime payload were byte-identical. Eleven installation records differed, comprising ten component manifests and the installation log. The collector checked that the manifests referred to the same paths relative to their respective prefixes. Cargo came from `7caf39914da1e28a67744ecbc963a5f26361474d`, rustc from `a4fa11bcd38280639cb94daacc125472657db6c3`. The executed Wild ELF digest was `0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5`. The bundled-tool digest in the upstream release manifest identifies its distributed asset.

## Ordinary Cargo commands

Each cell below gives full rustc processes, link-only rustc processes and stock Wild executions. Cold and independently clean runs started with both the target and shared build directories empty. The two counts of 62 other linkers on the cold whole-workspace builds are recorded separately in `workspace.json.gz`. Cargo’s logical freshness counts and the identities of every observed compiler and linker are preserved independently.

| Source and state | Focused, 300 units | Workspace, 619 units | Two notebook cases |
| --- | --- | --- | --- |
| Original, empty | 304 / 0 / 48 | 625 / 0 / 188 | Passed |
| Original, unchanged | 0 / 0 / 0 | 1 / 50 / 50 | Focused passed. Workspace ran the 200-test listing. |
| Reversed notebook edit | 2 / 0 / 1 | 12 / 43 / 52 | Both failed |
| Independently empty, edited | 304 / 0 / 48 | 625 / 0 / 188 | Both failed |
| Original source restored | 2 / 0 / 1 | 12 / 43 / 52 | Both passed |
| Original, unchanged again | 0 / 0 / 0 | 1 / 50 / 50 | Focused passed. Workspace ran the 200-test listing. |

The reversed change returned a hover for `Literal[1]` and an `int` inlay hint beyond the end of a notebook cell. The standalone e2e executables matched their respective independent edited references byte for byte and returned to their own original bytes after restoration. The workspace original was 226,518,976 bytes, SHA-256 `be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7`. The edited executable was 226,518,928 bytes, SHA-256 `d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8`.

The held workspace had a physical foreign-span marker in the regular `ron` depfile. Reading its marker child returned `ENOTDIR`. The translated `OBS1` record’s completeness byte was zero. On each unchanged workspace command the Ron archive kept its entire SHA-256 despite a new inode and mtime. The standalone metadata changed bytes and preserved its mtime. The test graph still included native searches outside the Ron archive.

## Native lookup in both installations

Each installation’s original capture contains the same 50 output basenames and 3,401 distinct explicit input paths. The two canonical build namespaces were `v2-0de3af5db4b086d2` for the inner installation and `v2-ed8a5e5c44d2fb2b` for the public outer installer. Every real linker’s `-L` argument pointed into its own namespace’s `psm` build output. Across the two baseline captures, 48 of 50 complete ELF digests matched. The `ruff` and `ty` CLI digests differed. The e2e complete ELF and its 394 explicit input count matched.

An initial negative control placed the test provider in the earlier installation’s directory while Cargo ran in the outer namespace. Its 50 stock linkers used the outer paths. Cargo succeeded and the control harness exited 1 when it failed to observe the intended process exit. The original diagnostic, Cargo output and trace-set digests are retained separately from the subsequent correctly targeted test.

| Earlier `psm/libgcc_s.so` in the active outer namespace | Cargo exit | Full / link-only / Wild | Executable observation |
| --- | ---: | --- | --- |
| Valid provider injecting a pre-init exit | 0 | 1 / 50 / 50 | All 50 actual executables exited 83 and listed no tests. |
| Malformed provider | 101 | 1 / 8 / 8 | The linker diagnosed `libgcc_s.so` and the deliberately invalid directive. |
| Provider removed after failure | 0 | 51 / 0 / 50 | The symbol disappeared from all 50 outputs. Every complete ELF matched its outer baseline. The selected executable listed 200 tests. |
| Subsequent unchanged chronology | 0 | 1 / 50 / 50 | All 50 GCC and collect2 processes reached stock Wild. Both selected notebook tests passed. |

A separate warm command used Wild’s native worker log. Of 50 real linkers, 47 had one worker, two had two workers and one had three. On that pass the selected e2e used two workers and produced a different complete ELF digest at the same size. The six-phase controlled e2e experiment below observed one worker on each selected invocation. Worker widths come from the corresponding physical command.

## Writable inputs and the single-archive edit

The original inner namespace’s physical input census found 3,396 user-modifiable or user-replaceable names comprising 1,420,620,362 bytes. The other five names were root-owned and accounted for 7,528 bytes. No input reported a verity or immutable inode. All 50 targets had a distinct writable native object and an absent higher-priority `libgcc_s.so` under one writable search directory. For the e2e target, the build user could change 389 of 394 explicit names.

A separate one-worker trial trained against sealed copies of the genuine inputs. With all names intact and the archive mtime preserved, replacing only `libty_server` with the real independently clean edited archive made the checker refuse. Stock Wild then produced the byte-exact edited workspace ELF. Restoring only that archive recovered the original ELF. The experiment also preserved an earlier valid native provider, a malformed provider and their genuine fallback behavior.

A separate six-command study ran the same ordinary workspace command with an experimental post-GCC checker for this one e2e executable. Three unchanged commands each ran one full and 50 link-only rustcs and 49 stock Wilds. The selected executable retained its bytes and inode. The driver advanced its mtime. The edited and restored runs both used stock Wild and matched the correct reference executables. The following unchanged run used all 50 stock Wilds after the linker recipe replaced all 139 enrolled CGU names. Their full object payload multisets matched. The checker recorded a generic refusal. The input census describes why this closed-input success does not establish a safe default on live, mutable workspaces. These records measure native job and correctness outcomes, without a wall-time claim.

## Verification

Run `python3 -IB verify.py` from any working directory. `focused.json.gz` and `workspace.json.gz` are the original portable six-phase packets. Their process records, Cargo artifact counts, relative output names, ELF sections and SHA-256s remain in the packets. `release.json` adds the release/download identities, two 50-command captures, 50 real width observations, active and misplaced provider tests, actual job exits and raw input commitments. For each shadow phase the digest of the complete filename-to-SHA256 trace map also binds empty and unsuccessful child traces. The custody and archive-control directories include their earlier independently sealed subsets.

`capsule.json` is a path-free projection of the separate six-command handoff packet, whose manifest is `938bc72b5fd4b269e0c8a8573ab70323b825cf242b743d6b22bd3758b9ee276d`. It includes all six physical process rosters, the 139 old and new object records, notebook outcomes and 100 separately observed process families. The stronger verifier can reproduce both projections from the retained evidence with `python3 -IB verify.py --originals STUDY_ROOT --capsule-originals HANDOFF_PACKET`. Those options require read access only. The packet contains digests of private raw streams alongside the public fields needed for offline checks. It omits original compiler environments and private filesystem prefixes.
