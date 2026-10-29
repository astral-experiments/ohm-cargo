# Cargo follows a relink-manifest symlink installed during an ordinary build

The published Ohm 1.99.0-19 Linux Cargo and the development Cargo for #282 replaced the contents of a separate, same-user sentinel with Cargo's generated relink manifest. The corrected Cargo from `5394ce8817e224971230b80a9066cc28d504ff94` replaced the symlink itself and preserved the sentinel's original inode and contents. All three real Cargo commands succeeded and the edited executable printed 29. The seven corresponding #282 and corrected output executables were byte-identical.

| When the symlink was installed | Published -19 | #282 combination | Corrected Cargo |
| --- | --- | --- | --- |
| After Cargo removed the old manifest, observed through `inotify` | Sentinel replaced | Sentinel replaced | Sentinel preserved |
| After the real compiler exited, by a test wrapper | Sentinel replaced | Sentinel replaced | Sentinel preserved |
| Before Cargo began the dirty build | Sentinel preserved | Sentinel preserved | Sentinel preserved |
| During a build with explicit `-Zrelink-only=no` | Sentinel preserved | Sentinel preserved | Sentinel preserved |
| During a build with explicit `-Zohm-defaults=no` | Sentinel preserved | Sentinel preserved | Sentinel preserved |

Each image ran seven traced commands, including two cold controls. Both the fixture and the watcher ran as uid 1000. The watcher used an inotify watch on the already-known manifest directory from the cold build. The dirty command made a genuine `main.rs` edit from 17 to 29. After the kernel reported deletion of the exact manifest entry, the watcher created the symlink there. Neither Cargo nor rustc was wrapped in this arm. On both affected images the same Cargo worker subsequently called `readlink` and renamed a temporary file over the distinct sentinel. On the correction it renamed over the manifest path. A later edit to 31 exercised the preinstalled-link control. All original file reads and writes used paths owned by the fixture user. The replay requires same-user ability to modify the private target directory during compilation.

The wrapper arm executed unmodified rustc and its real linker first, then installed the symlink on successful return. In the two disabled modes, the wrapper could leave a symlink in the output directory, but Cargo did not publish a manifest through it. The published all-defaults-off toolchain used its LLVM forwarding executable and `rust-lld`. The development toolchains used the system `ld` in that control. The native traces identify those distinct tools.

`RelinkCachePaths::write_manifest` in `src/compiler/mod.rs` previously called `cargo_util::paths::write_atomic`. That helper deliberately resolves a final symlink. The correction uses the existing `write_atomic_no_follow` and covers both callers of `write_manifest`. The operational cases here exercise initial manifest publication following successful full compilation. The comparison of two development Cargos used the same compiler frontend, driver and stock Wild. Only the Cargo executable changed. The official Linux release test used all of its published SDK components. Build identities and asset checksums are in `verdicts.json.gz`.

## Verify and reproduce

```sh
python3 -IB verify.py
python3 -IB reproduce.py /tmp/ohm-manifest-private-new --sdk /path/to/installed/sdk --expect follows
```

Use `--expect protected` with the corrected toolchain and a fresh directory. The standalone script runs cold, intervened and preinstalled-symlink builds through an ordinary `cargo +ohm build` on Linux. It uses its own offline Cargo home, target and build directories. Supplying `--sdk` links a private `+ohm` alias and leaves the installed SDK alone. This standalone script was also run independently against the published -19 and corrected images. Both three-command sequences matched their expected programs and filesystem outcomes.

`verdicts.json.gz` contains projected process and syscall records for all 21 matrix commands, hashes of the original streams, full program hashes and the six additional standalone results. The offline verifier verifies the component manifest and exercises four invalid mutations. `reconstruct.py` can regenerate the same projection from the retained private raw archive directories using `--only-sentinel --root <archive-parent> --green-raw-sha c53feaa932ca797f9401dfb7661f21aca02cef3d6ef429db9c65613bcdf7733a --export <new-file.gz>`. The first attempt encountered the real LLVM forwarding executable when classifying the all-defaults-off native command. The following attempt retained thirteen complete cases and then stopped on the additional `-C extra-filename` suffix in the development defaults-off wrapper. The final supplemental case bound the actual output name. All original stopped records and their completed cases remain available. No time estimate is derived here.
